"""Base class for all app. Scheduled by heartbeat. No interaction with user."""

import asyncio
import logging
import logging.config
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import time

import qzemoji as qe
from aioqzone.api.loginman import QRLoginMan, QrStrategy, UPLoginMan
from aioqzone.event.login import QREvent, UPEvent
from aioqzone.exception import LoginError
from aioqzone_feed.api import FeedApi, HeartbeatApi
from aioqzone_feed.event import FeedEvent, HeartbeatEvent
from aioqzone_feed.utils.task import AsyncTimer
from apscheduler.job import Job as APSJob
from apscheduler.triggers.interval import IntervalTrigger
from httpx import URL, HTTPError, Timeout
from qqqr.event import EventManager, Tasksets
from qqqr.exception import UserBreak
from qqqr.utils.net import ClientAdapter
from sqlalchemy.ext.asyncio import AsyncEngine
from telegram.constants import ParseMode
from telegram.error import NetworkError
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackContext,
    Defaults,
    ExtBot,
    Job,
)

from qzone3tg import AGREEMENT, DISCUSS
from qzone3tg.bot import ChatId
from qzone3tg.bot.queue import EditableQueue, QueueEvent
from qzone3tg.bot.splitter import FetchSplitter
from qzone3tg.settings import Settings, WebhookConf

from ..storage import StorageEvent, StorageMan
from ..storage.loginman import LoginMan

DISCUSS_HTML = f"<a href='{DISCUSS}'>Qzone2TG Discussion</a>"


class FakeLock(object):
    __slots__ = ()

    def acquire(self, _):
        pass


class TimeoutLoginman(LoginMan):
    def __init__(
        self,
        client: ClientAdapter,
        engine: AsyncEngine,
        uin: int,
        strategy: QrStrategy,
        pwd: str | None = None,
        refresh_time: int = 6,
        min_qr_interval: float = 0,
        min_up_interval: float = 0,
    ) -> None:
        super().__init__(client, engine, uin, strategy, pwd, refresh_time)
        self.qr_suppress_sec = min_qr_interval
        self.up_suppress_sec = min_up_interval
        self.suppress_qr_till = 0.0
        self.suppress_up_till = 0.0
        self.force_login = False

    def ordered_methods(self):
        if self.force_login:
            return super().ordered_methods()

        lmls = []
        for man in super().ordered_methods():
            match man:
                case UPLoginMan():
                    if not self.up_suppressed:
                        lmls.append(man)
                case QRLoginMan():
                    if not self.qr_suppressed:
                        lmls.append(man)
                case _:
                    lmls.append(man)
        return lmls

    @property
    def qr_suppressed(self):
        return time() < self.suppress_qr_till

    @property
    def up_suppressed(self):
        return time() < self.suppress_up_till

    @contextmanager
    def disable_suppress(self):
        self.force_login = True
        yield self
        self.force_login = False


class BaseApp(
    Tasksets,
    EventManager[FeedEvent, HeartbeatEvent, QREvent, UPEvent, StorageEvent, QueueEvent],
):
    start_time = 0

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
        super(Tasksets, self).__init__()
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        self.client = client
        self.engine = engine
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

        super(EventManager, self).__init__()  # update bases before instantiate hooks

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
    from ._hook import feedevent_hook as _sub_feedevent
    from ._hook import heartbeatevent_hook as _sub_heartbeatevent
    from ._hook import qrevent_hook as _sub_qrevent
    from ._hook import queueevent_hook as _sub_queueevent
    from ._hook import storageevent_hook as _sub_storageevent
    from ._hook import upevent_hook as _sub_upevent

    def init_qzone(self):
        conf = self.conf.qzone
        self.loginman = TimeoutLoginman(
            self.client,
            self.engine,
            conf.uin,
            conf.qr_strategy,
            conf.password.get_secret_value() if conf.password else None,
            min_qr_interval=conf.min_qr_interval,
            min_up_interval=conf.min_up_interval,
        )
        self.qzone = FeedApi(self.client, self.loginman, init_hb=False)
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
        self.queue = EditableQueue(
            self.bot,
            FetchSplitter(self.client),
            defaultdict(lambda: self.admin),
        )

    def init_timers(self):
        assert self.app.job_queue
        self.timers: dict[str, Job] = {}
        conf = self.conf.log

        # clean database
        async def clean(_):
            await self.hook_store.Clean(-self.conf.bot.storage.keepdays * 86400)

        self.timers["cl"] = self.app.job_queue.run_repeating(clean, 86400, 0, name="clean")

        async def lst_forever(_):
            self.log.info(self._status_text(True))
            return False

        self.timers["ls"] = self.app.job_queue.run_repeating(
            lst_forever, 3600, 3600, name="log status"
        )

        # register debug status timer
        if conf.debug_status_interval > 0:

            async def dst_forever(_):
                await BaseApp.status(self, self.admin, debug=True)
                return False

            self.timers["ds"] = self.app.job_queue.run_repeating(
                dst_forever,
                conf.debug_status_interval,
                conf.debug_status_interval,
                name="/status debug",
            )

        self.log.debug("init_timers done")

    def init_hooks(self):
        self.hook_qr = self.sub_of(QREvent)()
        self.hook_up = self.sub_of(UPEvent)()
        block = self.conf.qzone.block or []
        block = block.copy()
        if self.conf.qzone.block_self:
            block.append(self.conf.qzone.uin)

        self.hook_feed = self.sub_of(FeedEvent)()
        self.hook_queue = self.sub_of(QueueEvent)()
        self.hook_store = self.sub_of(StorageEvent)()
        self.hook_hb = self.sub_of(HeartbeatEvent)()

        self.qzone.register_hook(self.hook_feed)
        self.heartbeat.register_hook(self.hook_hb)
        self.queue.register_hook(self.hook_queue)
        self.loginman.register_hook(self.hook_qr)
        self.loginman.register_hook(self.hook_up)

        self.log.info("TG端初始化完成")

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

        return logging.getLogger(self.__class__.__name__)

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
            proxy = URL(proxy).copy_with(scheme="socks5")

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
        self.check_node()
        first_run = not await self.loginman.table_exists()
        self.log.info("注册信号处理...")
        self.register_signal()
        self.log.info("注册心跳...")
        self.heartbeat.add_heartbeat()
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
            task = self.add_hook_ref("command", self._fetch(self.admin))
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
        Return when :obj:`.app` is stopped.
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
            self.log.error("Node 不可用，二维码策略切换至 `force`.")
            self.conf.qzone.qr_strategy = QrStrategy.force
        elif not JSDOM.check_jsdom():
            self.log.warning("jsdom 不可用，可能无法提交验证码。")

    async def _fetch(self, to: ChatId, *, is_period: bool = False) -> None:
        """fetch feeds.

        :param to: send to whom
        :param is_period: triggered by heartbeat, defaults to False
        """
        if not is_period and not self.loginman.force_login:
            with self.loginman.disable_suppress():
                return await self._fetch(to, is_period=False)

        # No need to acquire lock since all fetch in BaseApp is triggered by heartbeat
        # which has 300s interval.
        # NOTE: subclass must handle async lock here
        self.log.info(f"Start fetch with period={is_period}")
        echo = lambda m: self.add_hook_ref("command", self.bot.send_message(to, m))
        # start a new batch
        self.queue.new_batch(self.qzone.new_batch())
        # fetch feed
        try:
            got = await self.qzone.get_feeds_by_second(self.conf.qzone.dayspac * 86400)
        except UserBreak:
            self.log.debug("Fetch stopped because UserBreak.")
            echo("命令已取消：用户取消了登录")
            return
        except LoginError:
            # LoginFailed hook will show reason to user
            self.log.warning("由于发生了登录错误，爬取未开始。")
            if self.heartbeat.hb_timer:
                self.heartbeat.hb_timer.stop()
                self.log.warning("由于发生了登录错误，心跳定时器已暂停。")
            else:
                self.log.warning(
                    "Should stop heartbeat because LoginError, but it has already stopped."
                )
            return
        except HTTPError as e:
            self.log.error(e)
            self.log.debug(e.request)
            echo(f"发生了网络错误: {e}")
            return
        except SystemError:
            return await self.shutdown()
        except:
            self.log.fatal("get_feeds_by_second：未捕获的异常", exc_info=True)
            return

        if got == 0:
            if not is_period:
                echo("您已跟上时代🎉")
            return

        # wait for all hook to finish
        await self.qzone.wait()
        got -= self.queue.skip_num
        if got == 0:
            if not is_period:
                echo("您已跟上时代🎉")
            return

        # forward
        try:
            await self.queue.send_all()
        except SystemError:
            return await self.shutdown()
        except:
            self.log.fatal("queue.send_all：未捕获的异常", exc_info=True)
            return

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
        echo(summary)

    async def license(self, to: ChatId):
        LICENSE_TEXT = f"""继续使用即代表您同意[用户协议]({AGREEMENT})。"""
        await self.bot.send_message(to, LICENSE_TEXT, parse_mode=ParseMode.MARKDOWN_V2)

    def _status_text(self, debug: bool, *, hf: bool = False):
        from aioqzone.utils.time import sementic_time

        ts2a = lambda ts: sementic_time(ts) if ts else "还是在上次"
        friendly = lambda b: ["🔴", "🟢"][int(b)] if hf else str(b)

        stat_dic = {
            "启动时间": ts2a(self.start_time),
            "上次登录": ts2a(self.loginman.last_login),
            "PTB应用状态": friendly(self.app.running),
            "PTB更新状态": friendly(self.app.updater and self.app.updater.running),
            "心跳状态": friendly(
                self.heartbeat.hb_timer and self.heartbeat.hb_timer.state == "PENDING"
            ),
            "上次心跳": ts2a(self.heartbeat.hb_timer and self.heartbeat.hb_timer.last_call),
            "上次清理数据库": ts2a(get_last_call(self.timers.get("cl"))),
            "二维码登录暂停至": ts2a(self.loginman.suppress_qr_till),
            "密码登录暂停至": ts2a(self.loginman.suppress_up_till),
        }
        if debug:
            add_dic = {}
            stat_dic.update(add_dic)
        return "\n".join(f"{k}: {v}" for k, v in stat_dic.items())

    async def status(self, to: ChatId, debug: bool = False):
        statm = self._status_text(debug, hf=True)
        dn = debug or self.conf.bot.default.disable_notification
        await self.bot.send_message(to, statm, disable_notification=dn)

    async def restart_heartbeat(self):
        """
        :return: `True` if heartbeat restarted. `False` if no need to restart / restart failed, etc.
        """
        if self.heartbeat.hb_timer is None:
            self.log.warning("heartbeat not initialized")
            return False

        self.log.debug("heartbeat state before restart: %s", self.heartbeat.hb_timer.state)
        if self.heartbeat.hb_timer.state != "PENDING":
            self.log.debug("heartbeat stopped. restarting...")
            self.heartbeat.hb_timer()
            self.log.debug("heartbeat state after restart: %s", self.heartbeat.hb_timer.state)
            if self.heartbeat.hb_timer.state == "PENDING":
                self.log.info("heartbeat restart success")
                return True
        return False


def get_last_call(timer: AsyncTimer | Job | APSJob | None) -> float:
    if timer is None:
        return 0.0
    if isinstance(timer, AsyncTimer):
        return timer.last_call
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
