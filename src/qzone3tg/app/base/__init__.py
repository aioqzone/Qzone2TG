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
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent, InlineKeyboardMarkup
from aiohttp import ClientConnectionError, ClientSession, ClientTimeout
from aioqzone.api import QrLoginManager, UpLoginManager
from aioqzone_feed.api import FeedApi
from aioqzone_feed.type import BaseFeed, FeedContent
from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from qzemoji.base import AsyncEngineFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError
from tylisten.futstore import FutureStore
from yarl import URL

from qzone3tg import AGREEMENT, DISCUSS
from qzone3tg.app.storage import StorageMan
from qzone3tg.app.storage.loginman import *
from qzone3tg.app.storage.orm import FeedOrm, MessageOrm
from qzone3tg.bot import ChatId
from qzone3tg.bot.queue import MsgQueue, is_mids
from qzone3tg.bot.splitter import FetchSplitter
from qzone3tg.settings import Settings, WebhookConf

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
        conf: Settings,
    ) -> None:
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        # future store channels
        self.ch_fetch = FutureStore()
        self.ch_db_write = FutureStore()
        self.ch_db_read = FutureStore()
        # init a fake lock since subclass impls this protocol but BaseApp needn't
        self.fetch_lock = asyncio.Lock()

        self.log = self._get_logger()
        self.silent_noisy_logger()

    async def __aenter__(self):
        self.client = await ClientSession().__aenter__()
        self.engine = await AsyncEngineFactory.sqlite3(self.conf.bot.storage.database).__aenter__()

        self.init_qzone()
        self.init_gram()
        self.init_timers()
        self.init_queue()
        self.init_hooks()

        return self

    async def __aexit__(self, *exc):
        await self.client.__aexit__(*exc)
        await self.engine.dispose()

    # --------------------------------
    #            properties
    # --------------------------------
    @property
    def admin(self):
        return self.conf.bot.admin

    # --------------------------------
    #             hook init
    # --------------------------------
    def init_qzone(self):
        conf = self.conf.qzone
        self.up_login = UpLoginManager(self.client, conf.up_config)
        self.qr_login = QrLoginManager(self.client, conf.qr_config)
        self.qzone = FeedApi(self.client, self.up_login)
        self.log.debug("init_qzone done")

    def init_gram(self):
        conf = self.conf.bot
        assert conf.token

        session = self._build_session()
        default: dict = dict(parse_mode=ParseMode.HTML)
        default |= conf.default.model_dump()

        self.dp = Dispatcher()
        self.bot = Bot(conf.token.get_secret_value(), session, **default)
        self.log.debug("init_gram done")

    def init_queue(self):
        self.store = StorageMan(self.engine)
        self.queue = MsgQueue(
            self.bot,
            FetchSplitter(self.client),
            defaultdict(lambda: self.admin),
        )

    def init_timers(self):
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start(paused=True)

        self.timers: dict[str, Job] = {}
        conf = self.conf.log

        async def heartbeat():
            if await self.qzone.heartbeat_refresh():
                # if heartbeat_refresh suggest to stop, we disable the job
                self.timers["hb"].pause()

        self.timers["hb"] = self.scheduler.add_job(
            heartbeat, "interval", minutes=5, id="heartbeat"
        )

        # clean database
        async def clean():
            await self.store.clean(-self.conf.bot.storage.keepdays * 86400)

        self.timers["cl"] = self.scheduler.add_job(clean, "interval", days=1, id="clean")

        async def lst_forever(_):
            self.log.info(self._status_dict(debug=True))

        self.timers["ls"] = self.scheduler.add_job(lst_forever, "interval", hours=1, id="status")

        # register debug status timer
        if conf.debug_status_interval > 0:
            self.timers["ds"] = self.scheduler.add_job(
                BaseApp.status,
                "interval",
                args=(self, self.admin),
                kwargs=dict(debug=True),
                id="debug_status",
                seconds=conf.debug_status_interval,
            )

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
    def _build_session(self) -> AiohttpSession | None:
        """(internal use only) Build netowrk args for PTB app.
        This will Set QzEmoji proxy as well.

        :param conf: NetworkConf from settings.
        :return: application builder

        .. versionchanged:: 0.5.0a1

            Pass in a builder instead of config. return the builder itself.
        """
        conf = self.conf.bot.network
        proxy = conf.proxy

        # TODO: default timeouts
        self.client._timeout = ClientTimeout(60, connect=conf.connect_timeout)

        if proxy and proxy.scheme == "socks5":
            self.log.warning("socks5 已替换为 socks5h")
            proxy = URL(str(proxy)).with_scheme("socks5h")

        if proxy:
            # expect to support https and socks
            proxy = str(proxy)
            return AiohttpSession(proxy=proxy)

    # --------------------------------
    #          graceful stop
    # --------------------------------
    def register_signal(self):
        def sigterm_handler(_signo, _stack_frame):
            raise KeyboardInterrupt

        import signal

        signal.signal(signal.SIGTERM, sigterm_handler)

        @self.dp.error()
        async def ptb_error_handler(event: ErrorEvent):
            if isinstance(event.exception, ClientConnectionError):
                self.log.fatal(f"请检查网络连接 ({event.exception})")
                if not self.conf.bot.network.proxy:
                    self.log.warning("提示：您是否忘记了设置代理？")
                if not isinstance(self.conf.bot.init_args, WebhookConf):
                    self.log.info("提示：使用 webhook 能够减少向 Telegram 发起连接的次数，从而间接降低代理出错的频率。")
                await self.shutdown()
                return

            self.log.fatal("PTB错误处理收到未被捕捉的异常：", exc_info=event.exception)

    async def shutdown(self):
        """Shutdown App. `@noexcept`

        .. versionchanged:: 0.5.0a2

            renamed to ``shutdown``
        """
        try:
            self.log.warning("App stopping...")
            self.qzone.stop()
            self.scheduler.shutdown(False)
            if self.dp._stop_signal:
                self.dp._stop_signal.set()

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
        first_run = not await table_exists(self.engine)
        self.log.info("注册信号处理...")
        self.register_signal()
        self.log.info("等待异步初始化任务...")

        cookie, _, _ = await asyncio.gather(
            load_cached_cookie(self.conf.qzone.uin, self.engine),
            qe.auto_update(),
            self.store.create(),
        )

        if first_run:
            await self.license(self.conf.bot.admin)

        if self.conf.bot.auto_start:
            await self.bot.send_message(self.admin, "Auto Start 🚀")
            self.ch_fetch.add_awaitable(self._fetch(self.admin))
        else:
            await self.bot.send_message(self.admin, "bot初始化完成，发送 /start 启动 🚀")

        self.log.info("启动所有定时器")
        self.scheduler.resume()

        self.start_time = time()
        return await self.idle()

    async def idle(self):
        """Idle. :exc:`asyncio.CancelledError` will be omitted.
        Return when :obj:`.app` is stopped.
        """
        assert self.dp._stopped_signal
        await self.dp._stopped_signal.wait()

    async def _fetch(self, to: ChatId, *, is_period: bool = False) -> None:
        """fetch feeds.

        :param to: send to whom
        :param is_period: triggered by heartbeat, defaults to False
        """
        if not self.fetch_lock.locked:
            async with self.fetch_lock:
                return await self._fetch(to, is_period=is_period)

        self.log.info(f"Start fetch with period={is_period}")
        echo = ""
        # start a new batch
        self.queue.new_batch(self.qzone.new_batch())
        # fetch feed
        got = -1
        try:
            got = await self.qzone.get_feeds_by_second(self.conf.qzone.dayspac * 86400)
        except RetryError:
            return

        if got == 0 and not is_period:
            echo = "您已跟上时代🎉"

        if echo:
            await self.bot.send_message(to, echo)
            echo = ""

        if got <= 0:
            return

        # wait for all hook to finish
        await asyncio.gather(self.qzone.ch_feed_dispatch.wait(), self.qzone.ch_feed_notify.wait())
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
            "上次密码登录": ts2a(self.up_login.last_login),
            "上次二维码登录": ts2a(self.qr_login.last_login),
            "PTB应用状态": friendly(self.dp._stopped_signal and not self.dp._stopped_signal.is_set()),
            "心跳状态": friendly(self.timers["hb"].next_run_time is not None),
            "上次心跳": ts2a(get_last_call(self.timers.get("hb"))),
            "上次清理数据库": ts2a(get_last_call(self.timers.get("cl"))),
        }
        if debug:
            add_dic = {}
            stat_dic.update(add_dic)
        return stat_dic

    async def status(self, to: ChatId, *, debug: bool = False):
        stat_dic = self._status_dict(debug=debug, hf=True)
        statm = "\n".join(f"{k}: {v}" for k, v in stat_dic.items())
        dn = debug or self.conf.bot.default.disable_notification
        await self.bot.send_message(to, statm, disable_notification=dn)

    async def restart_heartbeat(self, *_):
        """
        :return: `True` if heartbeat restarted. `False` if no need to restart / restart failed, etc.
        """
        if (job := self.timers.get("hb")) is None:
            self.log.warning("heartbeat not initialized")
            return False

        self.log.debug("heartbeat next_run_time before restart: %s", job.next_run_time)
        job.resume()
        self.log.debug("heartbeat next_run_time after restart: %s", job.next_run_time)
        return True


def get_last_call(timer: Job | None) -> float:
    if timer is None:
        return 0.0

    if not hasattr(timer, "next_run_time"):
        return 0.0
    if timer.next_run_time is None:
        return 0.0
    assert isinstance(timer.next_run_time, datetime)

    if not isinstance(timer.trigger, IntervalTrigger):
        return 0.0
    return (timer.next_run_time - timer.trigger.interval).timestamp()
