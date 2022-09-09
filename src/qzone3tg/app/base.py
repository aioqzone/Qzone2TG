"""Base class for all app. Scheduled by heartbeat. No interaction with user."""

import asyncio
import logging
import logging.config
from collections import defaultdict
from pathlib import Path
from time import time
from typing import Type, Union

import qzemoji as qe
import telegram.ext as ext
from aioqzone.api.loginman import QrStrategy
from aioqzone.exception import LoginError
from aioqzone_feed.api.feed import FeedApi
from httpx import URL
from qqqr.event import EventManager
from qqqr.exception import UserBreak
from qqqr.utils.net import ClientAdapter
from telegram.constants import ParseMode
from telegram.error import NetworkError
from telegram.ext import AIORateLimiter, Application, ApplicationBuilder, Job, JobQueue

from qzone3tg import DISCUSS, LICENSE
from qzone3tg.bot import ChatId
from qzone3tg.bot.atom import FetchSplitter, LocalSplitter
from qzone3tg.bot.limitbot import BotTaskEditter, RelaxSemaphore, SemaBot, TaskerEvent
from qzone3tg.bot.queue import EditableQueue
from qzone3tg.settings import LogConf, Settings, WebhookConf

from .hook import DefaultFeedHook, DefaultQrHook, DefaultUpHook
from .storage import AsyncEngine, DefaultStorageHook, StorageMan
from .storage.loginman import LoginMan

DISCUSS_HTML = f"<a href='{DISCUSS}'>Qzone2TG Discussion</a>"


class FakeLock(object):
    __slots__ = ()

    def acquire(self, _):
        pass


class BaseApp(
    EventManager[DefaultFeedHook, DefaultQrHook, DefaultUpHook, DefaultStorageHook, TaskerEvent]
):
    start_time = 0

    def __init__(self, client: ClientAdapter, engine: AsyncEngine, conf: Settings) -> None:
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        self.client = client
        self.engine = engine
        self.timers: dict[str, Job] = {}
        # init a fake lock since subclass impls this protocol but BaseApp needn't
        self.fetch_lock = FakeLock()
        self._get_logger(conf.log)
        self.silent_noisy_logger()

        self.loginman = LoginMan(
            client,
            engine,
            conf.qzone.uin,
            conf.qzone.qr_strategy,
            conf.qzone.password.get_secret_value() if conf.qzone.password else None,
        )
        self.qzone = FeedApi(client, self.loginman)
        self.log.info("Qzone端初始化完成")

        builder = Application.builder()
        # builder.rate_limiter(AIORateLimiter())
        builder = builder.token(conf.bot.token.get_secret_value())
        builder = builder.defaults(
            ext.Defaults(parse_mode=ParseMode.HTML, **conf.bot.default.dict())
        )
        builder = self._build_request(builder)

        self.app = builder.build()
        assert self.app.updater
        self.updater = self.app.updater
        self._set_timers()
        self.log.info("Bot初始化完成")

        super().__init__()  # update bases before instantiate hooks
        self.init_hooks()

    # --------------------------------
    #            properties
    # --------------------------------
    @property
    def admin(self):
        return self.conf.bot.admin

    @property
    def extbot(self):
        return self.app.bot

    @property
    def queue(self) -> JobQueue:
        return self.app.job_queue

    # --------------------------------
    #             hook init
    # --------------------------------
    def _sub_defaultqrhook(self, base: Type[DefaultQrHook]):
        class restart_timer(base):
            async def LoginSuccess(_self, meth):
                assert self.qzone.hb_timer
                if self.qzone.hb_timer.state != "PENDING":
                    self.qzone.hb_timer()
                await super().LoginSuccess(meth)

        return restart_timer

    def _sub_defaultfeedhook(self, base: Type[DefaultFeedHook]):
        class inner_feed_hook(base):
            async def HeartbeatRefresh(_self, num):
                await super().HeartbeatRefresh(num)
                return self.add_hook_ref(
                    "heartbeat", self.fetch(self.conf.bot.admin, is_period=True)
                )

            async def HeartbeatFailed(_self, exc: BaseException | None):
                await super().HeartbeatFailed(exc)
                info = f"({exc})" if exc else ""
                await self.bot.send_message(self.admin, "您的登录已过期，定时抓取功能暂时不可用" + info)

        return inner_feed_hook

    def init_hooks(self):
        sem = RelaxSemaphore(30)
        self.bot = SemaBot(self.extbot)
        self.hook_qr = self.sub_of(DefaultQrHook)(self.admin, self.bot)
        self.hook_up = self.sub_of(DefaultUpHook)(self.admin, self.bot)
        block = self.conf.qzone.block or []
        block = block.copy()
        if self.conf.qzone.block_self:
            block.append(self.conf.qzone.uin)

        self.hook_feed = self.sub_of(DefaultFeedHook)(
            EditableQueue(
                self.bot,
                BotTaskEditter(
                    FetchSplitter(self.client)
                    if self.conf.bot.send_gif_as_anim
                    else LocalSplitter(),
                    self.client,
                ),
                defaultdict(lambda: self.admin),
                sem,
            ),
            block or [],
        )
        self.hook_tasker = self.sub_of(TaskerEvent)()
        self.store = StorageMan(self.engine)
        self.hook_store = self.sub_of(DefaultStorageHook)(self.store)

        self.qzone.register_hook(self.hook_feed)
        self.hook_feed.queue.register_hook(self.hook_store)
        self.hook_feed.queue.tasker.register_hook(self.hook_tasker)
        self.loginman.register_hook(self.hook_qr)
        self.loginman.register_hook(self.hook_up)

        self.add_hook_ref = self.hook_feed.queue.add_hook_ref
        self.log.info("TG端初始化完成")

    # --------------------------------
    #           init logger
    # --------------------------------
    def _get_logger(self, conf: LogConf):
        """Build a logger from given config.

        :param conf: conf from settings.
        :return: the logger

        .. versionchanged:: 0.3.2

            :obj:`conf` will be read as a yaml file.

            .. seealso:: https://docs.python.org/3/library/logging.config.html#logging-config-dictschema
        """

        if conf.conf:
            if not conf.conf.exists():
                raise FileNotFoundError(conf.conf)
            import yaml

            with open(conf.conf, encoding="utf8") as f:
                dic = yaml.safe_load(f)
            assert isinstance(dic, dict)
            dic["disable_existing_loggers"] = False
            if "version" not in dic:
                dic["version"] = 1
            for hconf in dic.get("handlers", {}).values():
                if "filename" in hconf:
                    Path(hconf["filename"]).parent.mkdir(parents=True, exist_ok=True)
            logging.config.dictConfig(dic)
        else:
            logging.basicConfig(**conf.dict(include={"level", "format", "datefmt", "style"}))

        self.log = logging.getLogger(self.__class__.__name__)

    def _set_timers(self):
        conf = self.conf.log

        async def lst_forever(_):
            self.log.info(self._status_text(True))
            return False

        self.timers["ls"] = self.queue.run_repeating(lst_forever, 3600, 3600, name="log status")

        # register debug status timer
        if conf.debug_status_interval > 0:

            async def dst_forever(_):
                await BaseApp.status(self, self.admin, debug=True)
                return False

            self.timers["ds"] = self.queue.run_repeating(
                dst_forever,
                conf.debug_status_interval,
                conf.debug_status_interval,
                name="/status debug",
            )

    def silent_noisy_logger(self):
        """Silent some noisy logger in other packages."""

        if self.log.level >= logging.WARN or self.log.level == logging.DEBUG:
            return
        logging.getLogger("apscheduler.scheduler").setLevel(logging.WARN)
        logging.getLogger("apscheduler.executors.default").setLevel(logging.WARN)
        logging.getLogger("charset_normalizer").setLevel(logging.WARN)

    # --------------------------------
    #          init network
    # --------------------------------
    def _build_request(self, builder: ApplicationBuilder) -> ApplicationBuilder:
        """(internal use only) Build request_kwargs for PTB updater.
        This will Set QzEmoji proxy as well.

        :param conf: NetworkConf from settings.
        :return: request_kwargs

        .. versionchanged:: 0.5.0a1

            Pass in a builder instead of config. return the builder itself.
        """
        conf = self.conf.bot.network
        proxy = conf.proxy

        if proxy and proxy.scheme == "socks5h":
            # httpx resolves DNS at service-side by default. socks5h is not supported.
            self.log.warning("socks5h协议不受支持，已替换为socks5")
            proxy = URL(proxy).copy_with(scheme="socks5")

        if proxy:
            # expect to support https and socks
            proxy = str(proxy)
            builder = builder.proxy_url(proxy).get_updates_proxy_url(proxy)
            qe.proxy = proxy

        # TODO: default timeouts
        return builder

    # --------------------------------
    #          graceful stop
    # --------------------------------
    def register_signal(self):
        def sigterm_handler(_signo, _stack_frame):
            raise KeyboardInterrupt

        import signal

        signal.signal(signal.SIGTERM, sigterm_handler)

        async def ptb_error_handler(_, context: ext.CallbackContext):
            if isinstance(context.error, NetworkError):
                self.log.fatal(f"更新超时，请检查网络连接 ({context.error})")
                if not self.conf.bot.network.proxy:
                    self.log.warning("提示：您是否忘记了设置代理？")
                if not isinstance(self.conf.bot.init_args, WebhookConf):
                    self.log.info("提示：使用 webhook 能够减少向 Telegram 发起连接的次数，从而间接降低代理出错的频率。")
            else:
                self.log.fatal(
                    "Uncaught error caught by PTB error handler", exc_info=context.error
                )
            await self.shutdown()

        self.app.add_error_handler(ptb_error_handler)

    async def shutdown(self):
        """Shutdown App. `@noexcept`

        .. versionchanged:: 0.5.0a2

            renamed to ``shutdown``
        """
        try:
            self.log.warning("App stopping...")
            self.qzone.stop()
            if self.app.running:
                await self.app.stop()
            await self.app.shutdown()
            # for t in self.timers.values():
            #     t.schedule_removal()
        except (KeyboardInterrupt, asyncio.CancelledError, asyncio.TimeoutError):
            self.log.error("Force stopping...", exc_info=True)
            return
        except:
            self.log.error("Error when stopping.", exc_info=True)
            return

    # --------------------------------
    #              timer
    # --------------------------------
    def add_clean_task(self, keepdays: float, interval: float = 86400):
        """
        This function registers a timer that calls `self.clean(-keepdays * 86400)`
        every `interval` seconds.

        :param keepdays: Used to determine how many days worth of messages to keep.
        :return: the clean Task
        """

        async def clean(_):
            await self.hook_store.Clean(-keepdays * 86400)

        self.timers["cl"] = self.queue.run_repeating(clean, interval, 0, name="clean")

    # --------------------------------
    #          work logics
    # --------------------------------
    async def run(self):
        """
        The run function is the main entry point for your bot.
        It will be execute all async start-up preparation and finally call :meth:`.idle`.

        :return: None
        """
        self.check_node()
        first_run = not await self.loginman.table_exists()
        self.log.info("注册信号处理...")
        self.register_signal()
        self.log.info("注册心跳...")
        self.qzone.add_heartbeat()
        self.log.info("注册数据库清理任务...")
        self.add_clean_task(self.conf.bot.storage.keepdays)
        self.log.info("等待异步初始化任务...")
        init_task = [
            qe.auto_update(),
            self.store.create(),
            self.loginman.load_cached_cookie(),
        ]
        if not self.app._initialized:
            init_task.append(self.app.initialize())
        await asyncio.wait(init_task)
        await self.app.start()

        if first_run:
            await self.license(self.conf.bot.admin)

        if self.conf.bot.auto_start:
            await self.bot.send_message(self.admin, "Auto Start 🚀")
            task = self.add_hook_ref("command", self.fetch(self.admin))
            self.fetch_lock.acquire(task)
        else:
            await self.bot.send_message(self.admin, "bot初始化完成，发送 /start 启动 🚀")

        self.log.info("启动所有定时器")
        for t in self.timers.values():
            t.enabled = True
            self.log.debug(f"{t} started.")

        self.start_time = time()
        return await self.idle()

    async def idle(self):
        """Idle. :exc:`asyncio.CancelledError` will be omitted.
        Return when :obj:`.updater` is stopped.
        """
        while self.app._running:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                continue

    def check_node(self):
        if self.conf.qzone.qr_strategy == QrStrategy.force:
            return
        from shutil import which

        from jssupport.jsdom import JSDOM

        if not which("node"):
            self.log.error("Node not available, qr strategy switched to `force`.")
            self.conf.qzone.qr_strategy = QrStrategy.force
        elif not JSDOM.check_jsdom():
            self.log.warning("jsdom not available. Passing captcha may not work.")

    async def fetch(self, to: Union[int, str], *, is_period: bool = False):
        """fetch feeds.

        :param reload: dismiss existing records in database
        :param is_period: triggered by heartbeat, defaults to False

        :raises `SystemExist`: unexpected error
        """
        # No need to acquire lock since all fetch in BaseApp is triggered by heartbeat
        # which has 300s interval.
        # NOTE: subclass must handle async/threading lock here
        self.log.info(f"Start fetch with period={is_period}")
        echo = lambda m: self.add_hook_ref("command", self.bot.send_message(to, m))
        # start a new batch
        self.hook_feed.new_batch(self.qzone.new_batch())
        # fetch feed
        try:
            got = await self.qzone.get_feeds_by_second(
                self.conf.qzone.dayspac * 86400, exceed_pred=self.hook_store.Exists
            )
        except (UserBreak, LoginError):
            if self.qzone.hb_timer:
                self.qzone.hb_timer.stop()
            echo("命令已取消")
            return

        if got == 0:
            echo("您已跟上时代🎉")
            return

        # forward
        try:
            await self.qzone.wait()
            await self.hook_feed.queue.send_all()
        except:
            self.log.fatal("Unexpected exception in queue.send_all", exc_info=True)
            await self.shutdown()

        if is_period:
            return  # skip summary if this is called by heartbeat

        got -= self.hook_feed.queue.skip_num
        if got == 0:
            echo("您已跟上时代🎉")
            return

        # Since ForwardHook doesn't inform errors respectively, a summary of errs is sent here.
        errs = self.hook_feed.queue.exc_num
        log_level_helper = (
            f"\n当前日志等级为{self.log.level}, 将日志等级调整为 DEBUG 以获得完整调试信息。" if self.log.level > 10 else ""
        )
        summary = f"发送结束，共{got}条，{errs}条错误。"
        if errs:
            summary += f"查看服务端日志，在我们的讨论群 {DISCUSS_HTML} 寻求帮助。"
            summary += log_level_helper
        echo(summary)

    async def license(self, to: ChatId):
        LICENSE_TEXT = f"""继续使用即代表您同意[用户协议]({LICENSE})。"""
        await self.bot.send_message(to, LICENSE_TEXT, parse_mode=ParseMode.MARKDOWN_V2)

    def _status_text(self, debug: bool, *, hf: bool = False):
        from aioqzone.utils.time import sementic_time

        ts2a = lambda ts: sementic_time(ts) if ts else "还是在上次"
        friendly = lambda b: ["🔴", "🟢"][int(b)] if hf else str(b)

        stat_dic = {
            "启动时间": ts2a(self.start_time),
            "上次登录": ts2a(self.loginman.last_login),
            "心跳状态": friendly(self.qzone.hb_timer and self.qzone.hb_timer.state == "PENDING"),
            "上次心跳": ts2a(self.qzone.hb_timer and self.qzone.hb_timer.last_call),
            "上次清理数据库": ts2a(
                self.timers["cl"].next_t and self.timers["cl"].next_t.timestamp() - 86400
            ),
            "网速估计(Mbps)": round(self.hook_feed.queue.tasker.bps / 1e6, 2),
        }
        if debug:
            add_dic = {
                "updater.running": friendly(self.updater.running),
            }
            stat_dic.update(add_dic)
        return "\n".join(f"{k}: {v}" for k, v in stat_dic.items())

    async def status(self, to: ChatId, debug: bool = False):
        statm = self._status_text(debug, hf=True)
        dn = debug or self.conf.bot.default.disable_notification
        await self.bot.send_message(to, statm, disable_notification=dn)
