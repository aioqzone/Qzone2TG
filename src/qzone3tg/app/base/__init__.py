"""Base class for all app. Scheduled by heartbeat. No interaction with user."""

import asyncio
import logging
import logging.config
from collections import defaultdict
from datetime import datetime
from functools import partial
from pathlib import Path
from time import time

import qzemoji as qe  # 24.7->60M
import yaml
from aiogram import Bot, Dispatcher  # 60->171.7M
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import ErrorEvent, InlineKeyboardMarkup
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.formatting import BotCommand as CommandText
from aiogram.utils.formatting import Pre, Text, TextLink, as_key_value, as_list, as_marked_list
from aiohttp import ClientSession, ClientTimeout
from aioqzone.api import ConstLoginMan, QrLoginManager, UpLoginManager
from aioqzone.utils.time import sementic_time
from aioqzone_feed.api import FeedApi
from aioqzone_feed.type import FeedContent
from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from qzemoji.base import AsyncEngineFactory
from tenacity import RetryError
from tylisten.futstore import FutureStore

from qzone3tg import AGREEMENT, DISCUSS
from qzone3tg.app.storage import StorageMan, StorageMixin
from qzone3tg.app.storage.loginman import *
from qzone3tg.bot import ChatId
from qzone3tg.bot.queue import SendQueue, all_is_mid
from qzone3tg.bot.splitter import FetchSplitter
from qzone3tg.settings import Settings, WebhookConf

DISCUSS_HTML = TextLink("Qzone2TG Discussion", url=DISCUSS)


class BaseApp(StorageMixin):
    start_time = 0
    blockset: set[int]

    def __init__(
        self,
        conf: Settings,
    ) -> None:
        super().__init__()

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
        self._silent_noisy_logger()

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
        self.login = LoginManager(self.client, self.engine, conf.qr_config, conf.up_config)
        self.qzone = FeedApi(self.client, self.login, retry_if_login_expire=False)
        self.log.debug("init_qzone done")

    def init_gram(self):
        conf = self.conf.bot
        assert conf.token

        session = self._init_network()

        self.dp = Dispatcher()
        self.bot = Bot(conf.token.get_secret_value(), session)
        self.log.debug("init_gram done")

    def init_queue(self):
        self.store = StorageMan(self.engine)
        self.queue = SendQueue(
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

        async def lst_forever():
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
        from qzone3tg._hookspec import is_uin_blocked

        from ._hook import add_feed_impls, add_hb_impls, add_up_impls

        self.is_uin_blocked = is_uin_blocked()
        add_feed_impls(self)
        add_hb_impls(self)
        add_up_impls(self)

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
            logging.basicConfig(**conf.model_dump(include={"level", "format", "datefmt", "style"}))

        log = logging.getLogger(self.__class__.__name__)

        if conf.conf and not conf.conf.exists():
            log.error(f"{conf.conf.as_posix()} 不存在，已忽略此条目。")
        return log

    def _silent_noisy_logger(self):
        """Silent some noisy logger in other packages."""

        if self.log.level >= logging.WARN or self.log.level == logging.DEBUG:
            return

        for name in [
            "apscheduler.scheduler",
            "apscheduler.executors.default",
            "charset_normalizer",
            "aiosqlite",
            "aiohttp.server",
        ]:
            logging.getLogger(name).setLevel(logging.WARNING)

    # --------------------------------
    #          init network
    # --------------------------------
    def _init_network(self) -> AiohttpSession | None:
        """(internal use only) init interanl network settings.

        :param conf: NetworkConf from settings.
        :return: application builder

        .. versionchanged:: 0.5.0a1

            Pass in a builder instead of config. return the builder itself.
        """
        conf = self.conf.bot.network
        proxy = conf.proxy

        # TODO: default timeouts
        self.client._timeout = ClientTimeout(60, connect=conf.connect_timeout)

        if proxy:
            # expect to support https and socks
            session = AiohttpSession(proxy=str(proxy))
            if conf.rdns:
                session._connector_init["rdns"] = True
                self.log.warning("socks5 已替换为 socks5h")
            return session

    # --------------------------------
    #          graceful stop
    # --------------------------------
    def register_signal(self):
        def sigterm_handler(_signo, _stack_frame):
            raise KeyboardInterrupt

        import signal

        signal.signal(signal.SIGTERM, sigterm_handler)

        async def router_error_handler(event: ErrorEvent):
            if isinstance(event.exception, TelegramNetworkError):
                self.log.fatal(f"请检查网络连接 ({event.exception})")
                if not self.conf.bot.network.proxy:
                    self.log.warning("提示：您是否忘记了设置代理？")
                    await self.shutdown()
                if not isinstance(self.conf.bot.init_args, WebhookConf):
                    self.log.info(
                        "提示：使用 webhook 能够减少向 Telegram 发起连接的次数，从而间接降低代理出错的频率。"
                    )
                return

            self.log.fatal("router错误处理收到未被捕捉的异常：", exc_info=event.exception)

        self.dp.error.register(router_error_handler)
        for router in self.dp.sub_routers:
            router.error.register(router_error_handler)

    async def shutdown(self):
        """Shutdown App. `@noexcept`

        .. versionchanged:: 0.5.0a2

            renamed to ``shutdown``
        """
        try:
            self.log.warning("App stopping...")
            if isinstance(self.conf.bot.init_args, WebhookConf):
                if await self.bot.delete_webhook():
                    self.log.info("webhook deleted")
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
        first_run = not await self.login.table_exists()
        self.log.info("注册信号处理...")
        self.register_signal()
        self.log.info("等待异步初始化任务...")

        tasks = [
            qe.auto_update(),
            self.store.create(),
        ]

        if first_run:
            tasks.append(self.license(self.conf.bot.admin))
        else:
            tasks.append(self.login.load_cached_cookie())

        await asyncio.wait([asyncio.ensure_future(i) for i in tasks])

        self.log.info("启动所有定时器")
        self.scheduler.resume()

        if self.conf.bot.auto_start:
            await self.bot.send_message(self.admin, "Auto Start 🚀")
            self.ch_fetch.add_awaitable(self._fetch(self.admin))
        else:
            await self.bot.send_message(
                self.admin,
                **Text("初始化完成，发送", CommandText("/start"), "启动 🚀").as_kwargs(),
            )

        self.start_time = time()
        return await self.idle()

    async def idle(self):
        """Idle. :exc:`asyncio.CancelledError` will be omitted.
        Return when :obj:`.app` is stopped.
        """
        while True:
            await asyncio.sleep(0.25)

    async def _fetch(self, to: ChatId, *, is_period: bool = False) -> None:
        """fetch feeds.

        :param to: send to whom
        :param is_period: triggered by heartbeat, defaults to False
        """
        if not self.fetch_lock.locked:
            async with self.fetch_lock, ChatActionSender.typing(chat_id=to, bot=self.bot):
                return await self._fetch(to, is_period=is_period)

        self.log.info(f"Start fetch with period={is_period}")
        err_msg = Text()
        # start a new batch
        self.queue.new_batch(self.qzone.new_batch())
        # fetch feed
        got = -1
        try:
            got = await self.qzone.get_feeds_by_second(self.conf.qzone.dayspac * 86400)
        except RetryError as e:
            err_msg = Text("爬取失败 ", Pre(str(e.last_attempt.exception())))
        except BaseException as e:
            self.log.debug("未捕获的异常", exc_info=e)
            err_msg = Text("未捕获的异常 ", Pre(str(e)))

        if not is_period and not len(err_msg):
            # reschedule heartbeat timer
            self.timers["hb"].reschedule("interval", minutes=5)

        if got == 0 and not is_period:
            err_msg = Text("🎉")

        if (t := err_msg.render()) and t[0]:
            await self.bot.send_message(to, text=t[0], entities=t[1])

        if got <= 0:
            return

        # wait for all hook to finish
        await self.qzone.wait()
        got -= self.queue.drop_num
        if got <= 0:
            if not is_period:
                await self.bot.send_message(to, "🎉")
            return

        await self._send_save()

        if is_period:
            return  # skip summary if this is called by heartbeat

        # Since ForwardHook doesn't inform errors respectively, a summary of errs is sent here.
        errs = self.queue.exc_num
        summary = Text("发送结束，共", got, "条，", errs, "条错误。")
        if errs:
            summary = as_list(
                summary, Text("查看服务端日志，在我们的讨论群", DISCUSS_HTML, "寻求帮助。")
            )
            if self.log.level > 10:
                summary = as_list(
                    summary,
                    Text(
                        "当前日志等级为",
                        self.log.level,
                        "将日志等级调整为 DEBUG 以获得完整调试信息。",
                    ),
                )

        await self.bot.send_message(to, **summary.as_kwargs())

    async def _send_save(self):
        """wrap `.queue.send_all` with some post-sent database operation."""

        # forward
        def _post_sent(task: asyncio.Future[None], feed: FeedContent) -> None:
            if e := task.exception():
                return self.log.error(f"发送feed时出现错误：{feed}", exc_info=e)

            mids = self.queue.feed_state[feed]
            if not mids:
                return self.log.error(f"feed似乎未发送，请检查日志. fid={feed.fid}")
            assert all_is_mid(mids)
            self.ch_db_write.add_awaitable(self.SaveFeed(feed, mids))

        feed_send = self.queue.send_all()
        for feed, t in feed_send.items():
            t.add_done_callback(partial(_post_sent, feed=feed))
            if isinstance(feed.forward, FeedContent):
                t.add_done_callback(partial(_post_sent, feed=feed.forward))

        await asyncio.wait(feed_send.values())

    async def license(self, to: ChatId):
        LICENSE_TEXT = f"""继续使用即代表您同意<a href="{AGREEMENT}">用户协议</a>。"""
        await self.bot.send_message(to, LICENSE_TEXT)

    def _status_dict(self, *, debug: bool, hf: bool = False):
        """Generate app status dict.

        :param debug: include debug fields.
        :param hf: generate humuan-friendly value.
        :return: a status dict.
        """
        ts2a = lambda ts: sementic_time(ts) if ts else "还是在上次"
        friendly = lambda b: ["🔴", "🟢"][int(b)] if hf else str(b)

        stat_dic = {
            "启动时间": ts2a(self.start_time),
            "上次密码登录": ts2a(self.login.up.last_login),
            "上次二维码登录": ts2a(self.login.qr.last_login),
            "心跳状态": friendly(self.timers["hb"].next_run_time is not None),
            "上次心跳": ts2a(get_last_call(self.timers.get("hb"))),
            "上次清理数据库": ts2a(get_last_call(self.timers.get("cl"))),
        }
        if not isinstance(self.conf.bot.init_args, WebhookConf):
            stat_dic["polling"] = friendly(
                self.dp._stopped_signal and not self.dp._stopped_signal.is_set()
            )
        if debug:
            pass  # TODO: what can we add?
        return stat_dic

    async def status(self, to: ChatId, *, debug: bool = False):
        stat_dic = self._status_dict(debug=debug, hf=True)
        statm = as_marked_list(*(as_key_value(k, v) for k, v in stat_dic.items()))
        await self.bot.send_message(to, **statm.as_kwargs(), disable_notification=debug)

    def restart_heartbeat(self, *_):
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
    if not isinstance(timer.next_run_time, datetime):
        return 0.0

    if not isinstance(timer.trigger, IntervalTrigger):
        return 0.0
    return (timer.next_run_time - timer.trigger.interval).timestamp()
