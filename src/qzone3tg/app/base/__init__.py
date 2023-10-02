"""Base class for all app. Scheduled by heartbeat. No interaction with user."""

import asyncio
import logging
import logging.config
from collections import defaultdict
from datetime import datetime
from functools import partial
from pathlib import Path
from time import time

import qzemoji as qe
import yaml
from aiogram import InlineKeyboardMarkup
from aiogram.constants import ParseMode
from aiogram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackContext,
    Defaults,
    ExtBot,
    Job,
)
from aioqzone.exception import LoginError, QzoneError
from aioqzone_feed.api import HeartbeatApi
from aioqzone_feed.api.feed.h5 import FeedH5Api
from aioqzone_feed.type import BaseFeed, FeedContent
from apscheduler.job import Job as APSJob
from apscheduler.triggers.interval import IntervalTrigger
from httpx import URL, ConnectError, HTTPError, Timeout
from qqqr.exception import UserBreak
from qqqr.utils.net import ClientAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from tylisten.futstore import FutureStore

from qzone3tg import AGREEMENT, DISCUSS
from qzone3tg.bot import ChatId
from qzone3tg.bot.queue import MsgQueue, is_mids
from qzone3tg.bot.splitter import FetchSplitter
from qzone3tg.settings import Settings, WebhookConf

from ..storage import StorageMan
from ..storage.loginman import LoginMan
from ..storage.orm import FeedOrm, MessageOrm

DISCUSS_HTML = f"<a href='{DISCUSS}'>Qzone2TG Discussion</a>"


class FakeLock(object):
    __slots__ = ()

    def acquire(self, _):
        pass


class StorageMixin:
    store: StorageMan

    @property
    def sess_maker(self):
        return self.store.sess

    async def _update_message_ids(
        self,
        feed: BaseFeed,
        mids: list[int] | None,
        sess: AsyncSession | None = None,
        flush: bool = True,
    ):
        if sess is None:
            async with self.sess_maker() as newsess:
                await self._update_message_ids(feed, mids, sess=newsess, flush=flush)
            return

        if flush:
            await self._update_message_ids(feed, mids, sess=sess, flush=False)
            await sess.commit()
            return

        # query existing mids
        stmt = select(MessageOrm)
        stmt = stmt.where(*MessageOrm.fkey(feed))
        result = await sess.scalars(stmt)

        # delete existing mids
        tasks = [asyncio.create_task(sess.delete(i)) for i in result]
        if tasks:
            await asyncio.wait(tasks)

        if mids is None:
            return
        for mid in mids:
            sess.add(MessageOrm(uin=feed.uin, abstime=feed.abstime, mid=mid))

    async def SaveFeed(self, feed: BaseFeed, mids: list[int] | None = None):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param mids: message id list, defaults to None
        """

        async def _update_feed(feed, sess: AsyncSession):
            prev = await self.store.get_feed_orm(*FeedOrm.primkey(feed), sess=sess)
            if prev:
                # if exist: update
                FeedOrm.set_by(prev, feed)
            else:
                # not exist: add
                sess.add(FeedOrm.from_base(feed))

        async with self.sess_maker() as sess:
            async with sess.begin():
                # BUG: asyncio.wait/gather raises error at the end of a transaction
                await self._update_message_ids(feed, mids, sess=sess, flush=False)
                await _update_feed(feed, sess=sess)

    async def Mid2Feed(self, mid: int) -> BaseFeed | None:
        mo = await self.store.get_msg_orms(MessageOrm.mid == mid)
        if not mo:
            return
        orm = await self.store.get_feed_orm(
            FeedOrm.uin == mo[0].uin, FeedOrm.abstime == mo[0].abstime
        )
        if orm is None:
            return
        return BaseFeed(**orm.dict())  # type: ignore


class BaseApp(StorageMixin):
    start_time = 0
    blockset: set[int]

    def __init__(
        self,
        client: ClientAdapter,
        engine: AsyncEngine,
        conf: Settings,
        *,
        init_qzone=True,
        init_ptb=True,
        init_queue=True,
        init_hooks=True,
    ) -> None:
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        self.client = client
        self.engine = engine
        # future store channels
        self.ch_fetch = FutureStore()
        self.ch_db_write = FutureStore()
        self.ch_db_read = FutureStore()
        # init a fake lock since subclass impls this protocol but BaseApp needn't
        self.fetch_lock = FakeLock()

        self.log = self._get_logger()
        self.silent_noisy_logger()

        if init_qzone:
            self.init_qzone()

        if init_ptb:
            self.init_ptb()
            self.init_timers()

        if init_queue:
            self.init_queue()

        if init_hooks:
            self.init_hooks()

    # --------------------------------
    #            properties
    # --------------------------------
    @property
    def admin(self):
        return self.conf.bot.admin

    @property
    def bot(self) -> ExtBot:
        return self.app.bot

    # --------------------------------
    #             hook init
    # --------------------------------
    def init_qzone(self):
        conf = self.conf.qzone
        self.loginman = LoginMan(
            client=self.client,
            engine=self.engine,
            up_config=conf.up_config,
            qr_config=conf.qr_config,
            h5=True,
        )
        self.qzone = FeedH5Api(self.client, self.loginman, init_hb=False)
        self.heartbeat = HeartbeatApi(self.qzone)
        self.log.debug("init_qzone done")

    def init_ptb(self):
        conf = self.conf.bot
        assert conf.token

        builder = Application.builder()
        builder.rate_limiter(AIORateLimiter())
        builder = builder.token(conf.token.get_secret_value())
        builder = builder.defaults(Defaults(parse_mode=ParseMode.HTML, **conf.default.dict()))
        builder = self._build_request(builder)

        self.app = builder.build()
        self.log.debug("init_ptb done")

    def init_queue(self):
        self.store = StorageMan(self.engine)
        self.queue = MsgQueue(
            self.bot,
            FetchSplitter(self.client),
            defaultdict(lambda: self.admin),
        )

    def init_timers(self):
        job_queue = self.app.job_queue
        assert job_queue
        self.timers: dict[str, Job] = {}
        conf = self.conf.log

        async def heartbeat(_):
            if await self.heartbeat.heartbeat_refresh():
                # if heartbeat_refresh suggest to stop, we disable the job
                self.timers["hb"].enabled = False

        self.timers["hb"] = job = job_queue.run_repeating(
            heartbeat, interval=300, first=300, name="heartbeat"
        )
        job.enabled = False

        # clean database
        async def clean(_):
            await self.store.clean(-self.conf.bot.storage.keepdays * 86400)

        self.timers["cl"] = job = job_queue.run_repeating(clean, 86400, 0, name="clean")
        job.enabled = False

        async def lst_forever(_):
            self.log.info(self._status_dict(debug=True))

        self.timers["ls"] = job_queue.run_repeating(lst_forever, 3600, 3600, name="status")

        # register debug status timer
        if conf.debug_status_interval > 0:

            async def dst_forever(_):
                await BaseApp.status(self, self.admin, debug=True)

            self.timers["ds"] = job = job_queue.run_repeating(
                dst_forever,
                conf.debug_status_interval,
                conf.debug_status_interval,
                name="debug_status",
            )
            job.enabled = False

        self.log.debug("init_timers done")

    def init_hooks(self):
        from ._hook import feedevent_hook, heartbeatevent_hook, qrevent_hook, upevent_hook

        feedevent_hook(self)
        heartbeatevent_hook(self)
        qrevent_hook(self)
        upevent_hook(self)

        self.log.info("TG端初始化完成")

    def _make_qr_markup(self) -> InlineKeyboardMarkup | None:
        return

    # --------------------------------
    #           init logger
    # --------------------------------
    def _get_logger(self):
        """Build a logger from given config.

        :param conf: conf from settings.
        :return: the logger

        .. versionchanged:: 0.3.2

            :obj:`conf` will be read as a yaml file.

            .. seealso:: https://docs.python.org/3/library/logging.config.html#logging-config-dictschema
        """
        conf = self.conf.log

        if conf.conf and conf.conf.exists():
            with open(conf.conf, encoding="utf8") as f:
                dic = yaml.safe_load(f)
            if not isinstance(dic, dict):
                raise TypeError(f"请检查日志配置：{conf.conf}", type(dic))

            dic["disable_existing_loggers"] = False
            if "version" not in dic:
                dic["version"] = 1
            for hconf in dic.get("handlers", {}).values():
                if "filename" in hconf:
                    Path(hconf["filename"]).parent.mkdir(parents=True, exist_ok=True)
            logging.config.dictConfig(dic)
        else:
            logging.basicConfig(**conf.dict(include={"level", "format", "datefmt", "style"}))

        log = logging.getLogger(self.__class__.__name__)

        if conf.conf and not conf.conf.exists():
            log.error(f"{conf.conf.as_posix()} 不存在，已忽略此条目。")
        return log

    def silent_noisy_logger(self):
        """Silent some noisy logger in other packages."""

        if self.log.level >= logging.WARN or self.log.level == logging.DEBUG:
            return
        logging.getLogger("apscheduler.scheduler").setLevel(logging.WARN)
        logging.getLogger("apscheduler.executors.default").setLevel(logging.WARN)
        logging.getLogger("charset_normalizer").setLevel(logging.WARN)
        logging.getLogger("aiosqlite").setLevel(logging.WARN)
        logging.getLogger("hpack.hpack").setLevel(logging.WARN)

    # --------------------------------
    #          init network
    # --------------------------------
    def _build_request(self, builder: ApplicationBuilder) -> ApplicationBuilder:
        """(internal use only) Build netowrk args for PTB app.
        This will Set QzEmoji proxy as well.

        :param conf: NetworkConf from settings.
        :return: application builder

        .. versionchanged:: 0.5.0a1

            Pass in a builder instead of config. return the builder itself.
        """
        conf = self.conf.bot.network
        proxy = conf.proxy

        if proxy and proxy.scheme == "socks5h":
            # httpx resolves DNS at service-side by default. socks5h is not supported.
            self.log.warning("socks5h协议不受支持，已替换为socks5")
            proxy = URL(str(proxy)).copy_with(scheme="socks5")

        if proxy:
            # expect to support https and socks
            proxy = str(proxy)
            builder = builder.proxy_url(proxy).get_updates_proxy_url(proxy)
            qe.proxy = proxy

        # TODO: default timeouts
        self.client.client.timeout = Timeout(60, connect=conf.connect_timeout)
        builder = builder.connect_timeout(conf.connect_timeout).read_timeout(60).write_timeout(60)
        return builder

    # --------------------------------
    #          graceful stop
    # --------------------------------
    def register_signal(self):
        def sigterm_handler(_signo, _stack_frame):
            raise KeyboardInterrupt

        import signal

        signal.signal(signal.SIGTERM, sigterm_handler)

        async def ptb_error_handler(_, context: CallbackContext):
            if isinstance(context.error, ConnectError):
                self.log.fatal(f"请检查网络连接 ({context.error})")
                if not self.conf.bot.network.proxy:
                    self.log.warning("提示：您是否忘记了设置代理？")
                if not isinstance(self.conf.bot.init_args, WebhookConf):
                    self.log.info("提示：使用 webhook 能够减少向 Telegram 发起连接的次数，从而间接降低代理出错的频率。")
                await self.shutdown()
                return

            self.log.fatal("PTB错误处理收到未被捕捉的异常：", exc_info=context.error)

        self.app.add_error_handler(ptb_error_handler)

    async def shutdown(self):
        """Shutdown App. `@noexcept`

        .. versionchanged:: 0.5.0a2

            renamed to ``shutdown``
        """
        try:
            self.log.warning("App stopping...")
            self.qzone.stop()
            self.heartbeat.stop()
            for t in self.timers.values():
                if not t.removed:
                    t.schedule_removal()
            if self.app.running:
                await self.app.stop()
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
            await self.app.shutdown()

        except (KeyboardInterrupt, asyncio.CancelledError, asyncio.TimeoutError):
            self.log.error("Force stopping...", exc_info=True)
            return
        except:
            self.log.error("Error when stopping.", exc_info=True)
            return

    # --------------------------------
    #          work logics
    # --------------------------------
    async def run(self):
        """
        The run function is the main entry point for your bot.
        It will be execute all async start-up preparation and finally call :meth:`.idle`.

        :return: None
        """
        first_run = not await self.loginman.table_exists()
        self.log.info("注册信号处理...")
        self.register_signal()
        self.log.info("等待异步初始化任务...")
        init_task = [
            qe.auto_update(),
            self.store.create(),
            self.loginman.load_cached_cookie(),
        ]
        if not self.app._initialized:
            init_task.append(self.app.initialize())
        await asyncio.wait([asyncio.create_task(i) for i in init_task])
        await self.app.start()

        if first_run:
            await self.license(self.conf.bot.admin)

        if self.conf.bot.auto_start:
            await self.bot.send_message(self.admin, "Auto Start 🚀")
            task = self.ch_fetch.add_awaitable(self._fetch(self.admin))
            self.fetch_lock.acquire(task)
        else:
            await self.bot.send_message(self.admin, "bot初始化完成，发送 /start 启动 🚀")

        self.log.info("启动所有定时器")
        for t in self.timers.values():
            t.enabled = True
            self.log.debug(f"Job <{t.name}> started.")

        self.start_time = time()
        return await self.idle()

    async def idle(self):
        """Idle. :exc:`asyncio.CancelledError` will be omitted.
        Return when :obj:`.app` is stopped.
        """
        while self.app._running:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                continue

    async def _fetch(self, to: ChatId, *, is_period: bool = False) -> None:
        """fetch feeds.

        :param to: send to whom
        :param is_period: triggered by heartbeat, defaults to False
        """
        if not is_period:
            with self.loginman.force_login():
                return await self._fetch(to, is_period=False)

        # No need to acquire lock since all fetch in BaseApp is triggered by heartbeat
        # which has 300s interval.
        # NOTE: subclass must handle async lock here
        self.log.info(f"Start fetch with period={is_period}")
        echo = ""
        # start a new batch
        self.queue.new_batch(self.qzone.new_batch())
        # fetch feed
        got = -1
        try:
            got = await self.qzone.get_feeds_by_second(self.conf.qzone.dayspac * 86400)
        except* UserBreak:
            self.log.info("用户取消了登录")
            echo = "命令已取消：用户取消了登录"
        except* LoginError:
            # LoginFailed hook will show reason to user
            self.log.warning("由于发生了登录错误，爬取未开始。")
            self.timers["hb"].enabled = False
            self.log.warning("由于发生了登录错误，心跳定时器已暂停。")
        except* QzoneError as e:
            self.log.warning(f"get_feeds_by_second: QzoneError", exc_info=True)
            echo = "Qzone未正常提供服务。通常这并不意味着程序发生了错误。这种情况可能持续几小时或数天。"
        except* HTTPError:
            self.log.error("get_feeds_by_second 抛出了异常", exc_info=True)
            echo = "有错误发生，但Qzone3TG 或许能继续运行。请检查日志以获取详细信息。"
        except* BaseException:
            self.log.fatal("get_feeds_by_second：未捕获的异常", exc_info=True)
            echo = "有错误发生，Qzone3TG 或许不能继续运行。请检查日志以获取详细信息。"

        if got == 0 and not is_period:
            echo = "您已跟上时代🎉"

        if echo:
            await self.bot.send_message(to, echo)
            echo = ""

        if got <= 0:
            return

        # wait for all hook to finish
        await asyncio.gather(self.qzone.ch_dispatch.wait(), self.qzone.ch_notify.wait())
        got -= self.queue.skip_num
        if got <= 0:
            if not is_period:
                await self.bot.send_message(to, "您已跟上时代🎉")
            return

        # forward
        def _post_sent(task: asyncio.Future[None], feed: FeedContent):
            if e := task.exception():
                return self.log.error(f"发送feed时出现错误：{feed}", exc_info=e)

            mids = self.queue.Q[feed]
            assert is_mids(mids)
            self.ch_db_write.add_awaitable(self.SaveFeed(feed, mids))

        feed_send = self.queue.send_all()
        for feed, t in feed_send.items():
            t.add_done_callback(partial(_post_sent, feed=feed))
            if isinstance(feed.forward, FeedContent):
                t.add_done_callback(partial(_post_sent, feed=feed.forward))

        await self.queue.wait_all()

        if is_period:
            return  # skip summary if this is called by heartbeat

        # Since ForwardHook doesn't inform errors respectively, a summary of errs is sent here.
        errs = self.queue.exc_num
        log_level_helper = (
            f"\n当前日志等级为{self.log.level}, 将日志等级调整为 DEBUG 以获得完整调试信息。" if self.log.level > 10 else ""
        )
        summary = f"发送结束，共{got}条，{errs}条错误。"
        if errs:
            summary += f"查看服务端日志，在我们的讨论群 {DISCUSS_HTML} 寻求帮助。"
            summary += log_level_helper

        await self.bot.send_message(to, summary)

    async def license(self, to: ChatId):
        LICENSE_TEXT = f"""继续使用即代表您同意<a href="{AGREEMENT}">用户协议</a>。"""
        await self.bot.send_message(to, LICENSE_TEXT)

    def _status_dict(self, *, debug: bool, hf: bool = False):
        """Generate app status dict.

        :param debug: include debug fields.
        :param hf: generate humuan-friendly value.
        :return: a status dict.
        """
        from aioqzone.utils.time import sementic_time

        ts2a = lambda ts: sementic_time(ts) if ts else "还是在上次"
        friendly = lambda b: ["🔴", "🟢"][int(b)] if hf else str(b)

        stat_dic = {
            "启动时间": ts2a(self.start_time),
            "上次登录": ts2a(self.loginman.last_login),
            "PTB应用状态": friendly(self.app.running),
            "PTB更新状态": friendly(self.app.updater and self.app.updater.running),
            "心跳状态": friendly(self.timers.get("hb") and self.timers["hb"].enabled),
            "上次心跳": ts2a(get_last_call(self.timers.get("hb"))),
            "上次清理数据库": ts2a(get_last_call(self.timers.get("cl"))),
            "二维码登录暂停至": ts2a(self.loginman.qr_suppress_end_time),
            "密码登录暂停至": ts2a(self.loginman.up_suppress_end_time),
        }
        if debug:
            add_dic = {}
            stat_dic.update(add_dic)
        return stat_dic

    async def status(self, to: ChatId, debug: bool = False):
        stat_dic = self._status_dict(debug=debug, hf=True)
        statm = "\n".join(f"{k}: {v}" for k, v in stat_dic.items())
        dn = debug or self.conf.bot.default.disable_notification
        await self.bot.send_message(to, statm, disable_notification=dn)

    async def restart_heartbeat(self, *_):
        """
        :return: `True` if heartbeat restarted. `False` if no need to restart / restart failed, etc.
        """
        if self.timers.get("hb") is None:
            self.log.warning("heartbeat not initialized")
            return False

        self.log.debug("heartbeat state before restart: %s", self.timers["hb"].enabled)
        self.timers["hb"].enabled = True
        self.log.debug("heartbeat state after restart: %s", self.timers["hb"].enabled)
        return True


def get_last_call(timer: Job | APSJob | None) -> float:
    if timer is None:
        return 0.0
    if isinstance(timer, Job):
        timer = timer.job

    if not hasattr(timer, "next_run_time"):
        return 0.0
    if timer.next_run_time is None:
        return 0.0
    assert isinstance(timer.next_run_time, datetime)

    if not isinstance(timer.trigger, IntervalTrigger):
        return 0.0
    return (timer.next_run_time - timer.trigger.interval).timestamp()
