"""Base class for all app. Scheduled by heartbeat. No interaction with user."""

import asyncio
import logging
import logging.config
from collections import defaultdict
from pathlib import Path
from typing import Type, Union, cast

import qzemoji as qe
import telegram as tg
import telegram.ext as ext
from aiohttp import ClientSession as Session
from aioqzone.exception import LoginError
from aioqzone_feed.api.feed import FeedApi
from pydantic import AnyUrl
from qqqr.exception import UserBreak

from qzone3tg import DISCUSS
from qzone3tg.bot import ChatId
from qzone3tg.bot.atom import FetchSplitter, LocalSplitter
from qzone3tg.bot.limitbot import BotTaskEditter, RelaxSemaphore, SemaBot
from qzone3tg.bot.queue import EditableQueue
from qzone3tg.settings import LogConf, NetworkConf, Settings

from .hook import DefaultFeedHook, DefaultQrHook
from .storage import AsyncEngine, DefaultStorageHook
from .storage.loginman import LoginMan

DISCUSS_HTML = f"<a href='{DISCUSS}'>Qzone2TG Discussion</a>"


class BaseApp:
    def __init__(self, sess: Session, engine: AsyncEngine, conf: Settings) -> None:
        super().__init__()
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        self.sess = sess
        self.engine = engine
        self._get_logger(conf.log)
        self.silent_noisy_logger()

        self.loginman = LoginMan(
            sess,
            engine,
            conf.qzone.uin,
            conf.qzone.qr_strategy,
            conf.qzone.password.get_secret_value() if conf.qzone.password else None,
        )
        self.qzone = FeedApi(sess, self.loginman)
        self.log.info("Qzone端初始化完成")

        self.updater = ext.Updater(
            token=conf.bot.token.get_secret_value(),
            defaults=ext.Defaults(
                parse_mode=tg.ParseMode.HTML, run_async=False, **conf.bot.default.dict()
            ),
            request_kwargs=self._request_args(conf.bot.network),
            workers=0,
        )
        self.init_hooks()

    # --------------------------------
    #            properties
    # --------------------------------
    @property
    def admin(self):
        return self.conf.bot.admin

    @property
    def tgbot(self):
        return self.updater.bot

    # --------------------------------
    #             hook init
    # --------------------------------
    @property
    def _qr_hook_cls(self) -> Type[DefaultQrHook]:
        class inner_qr_hook(DefaultQrHook):
            async def LoginSuccess(*a):
                if self.qzone.hb_timer.state != "PENDING":
                    self.qzone.hb_timer()
                await super().LoginSuccess()

        return inner_qr_hook

    @property
    def _storage_hook_cls(self) -> Type[DefaultStorageHook]:
        return DefaultStorageHook

    @property
    def _feed_hook_cls(self) -> Type[DefaultFeedHook]:
        class inner_feed_hook(DefaultFeedHook):
            async def HeartbeatRefresh(_, num):
                await super().HeartbeatRefresh(num)
                return self.add_hook_ref(
                    "heartbeat", self.fetch(self.conf.bot.admin, is_period=True)
                )

        return inner_feed_hook

    def init_hooks(self):
        sem = RelaxSemaphore(30)
        self.bot = SemaBot(self.tgbot, sem)
        self.hook_qr = self._qr_hook_cls(self.admin, self.bot)
        block = self.conf.qzone.block or []
        block = block.copy()
        if self.conf.qzone.block_self:
            block.append(self.conf.qzone.uin)
        self.hook_feed = self._feed_hook_cls(
            EditableQueue(
                BotTaskEditter(
                    self.tgbot,
                    FetchSplitter(self.sess)
                    if self.conf.bot.send_gif_as_anim
                    else LocalSplitter(),
                    self.sess,
                ),
                defaultdict(lambda: self.admin),
                sem,
            ),
            block or [],
        )
        self.store = self._storage_hook_cls(self.engine)
        self.qzone.register_hook(self.hook_feed)
        self.hook_feed.queue.register_hook(self.store)
        self.loginman.register_hook(self.hook_qr)

        self.add_hook_ref = self.hook_feed.queue.add_hook_ref
        self.log.info("TG端初始化完成")

    # --------------------------------
    #           init logger
    # --------------------------------
    def _get_logger(self, conf: LogConf):
        """(internal use only) Build a logger from given config.

        :param conf: conf from settings.
        :return: the logger
        """

        if conf.conf:
            while True:
                try:
                    logging.config.fileConfig(conf.conf, disable_existing_loggers=False)
                except FileNotFoundError as e:
                    if not (p := Path(e.filename).parent).exists():
                        p.mkdir(parents=True)
                    else:
                        raise e
                else:
                    break
        else:
            default = {
                "format": "[%(levelname)s] %(asctime)s %(name)s: %(message)s",
                "datefmt": "%Y %b %d %H:%M:%S",
                "level": "INFO",
            }
            default.update(conf.dict())
            default.pop("conf", None)
            logging.basicConfig(**default)

        self.log = logging.getLogger(self.__class__.__name__)
        return self.log

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
    def _request_args(self, conf: NetworkConf) -> dict:
        """(internal use only) Build request_kwargs for PTB updater.

        :param conf: NetworkConf from settings.
        :return: request_kwargs
        """

        args = {}
        proxy = conf.proxy
        if proxy and str.startswith(proxy.scheme, "socks"):
            if proxy.user:
                args["urllib3_proxy_kwargs"] = {
                    "urllib3_proxy_kwargs": proxy.user,
                    "urllib3_proxy_kwargs": proxy.password,
                }
            proxy = AnyUrl.build(
                scheme=proxy.scheme,
                host=proxy.host or "",
                tld=proxy.tld or "",
                port=proxy.port,
                path=proxy.path,
                query=proxy.query,
                fragment=proxy.fragment,
            )
        if proxy:
            args["proxy_url"] = proxy
        return args

    # --------------------------------
    #          graceful stop
    # --------------------------------
    def register_signal(self):
        def sigterm_handler(_signo, _stack_frame):
            raise KeyboardInterrupt

        import signal

        signal.signal(signal.SIGTERM, sigterm_handler)

    def stop(self):
        self.qzone.stop()
        self.updater.stop()

    # --------------------------------
    #          work logics
    # --------------------------------
    async def run(self):
        """Run the app. Current thread will be blocked until KeyboardInterrupt is raised
        or `loop.stop()` is called."""

        first_run = not await self.loginman.table_exists()
        self.log.info("注册信号处理...")
        self.register_signal()
        self.log.info("注册心跳...")
        self.qzone.add_heartbeat()
        self.log.info("注册数据库清理任务...")
        self.store.add_clean_task(self.conf.bot.storage.keepdays)
        self.log.info("等待异步初始化任务...")
        qe.proxy = self.conf.bot.network.proxy and str(self.conf.bot.network.proxy)
        init_task = [qe.auto_update(), self.store.create(), self.loginman.load_cached_cookie()]
        await asyncio.wait(init_task)

        if first_run:
            await self.license(self.conf.bot.admin)

        await self.bot.send_message(self.conf.bot.admin, "bot初始化完成，发送 /start 启动 🚀")

        # idle
        while True:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                continue

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
                self.conf.qzone.dayspac * 86400, exceed_pred=self.store.exists
            )
        except (UserBreak, LoginError):
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
            exit(1)

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
        from telegram.parsemode import ParseMode

        LICENSE_TEXT = """用户协议"""
        await self.bot.send_message(to, LICENSE_TEXT, parse_mode=ParseMode.MARKDOWN_V2)

    async def status(self, to: ChatId):
        from aioqzone.utils.time import sementic_time

        ts2a = lambda ts: sementic_time(ts) if ts else "还是在上次"
        stat_dic = {
            "上次登录": ts2a(self.loginman.last_login),
            "心跳状态": "🟢" if self.qzone.hb_timer.state == "PENDING" else "🔴",
            "上次心跳": ts2a(self.qzone.hb_timer.last_call),
            "上次清理数据库": ts2a(self.store.cl.last_call),
        }
        statm = "\n".join(f"{k}: {v}" for k, v in stat_dic.items())
        await self.bot.send_message(to, statm)
