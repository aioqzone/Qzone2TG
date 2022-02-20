"""Base class for all app. Scheduled by heartbeat. No interaction with user."""

import asyncio
import logging
import logging.config
from pathlib import Path
from typing import cast, Union

from aiohttp import ClientSession as Session
from aioqzone.exception import LoginError
from aioqzone_feed.api.feed import FeedApi
from pydantic import AnyUrl
from qqqr.exception import UserBreak
import qzemoji as qe
from telegram import ParseMode
from telegram.ext import Defaults
from telegram.ext import Updater

from qzone3tg import DISCUSS
from qzone3tg.settings import LogConf
from qzone3tg.settings import NetworkConf
from qzone3tg.settings import Settings
from qzone3tg.utils.iter import anext

from ..bot.limitbot import ChatId
from .hook import BaseAppHook
from .storage import AsyncEngine
from .storage import DefaultStorageHook
from .storage.loginman import LoginMan

DISCUSS_HTML = f"<a href='{DISCUSS}'>Qzone2TG Discussion</a>"


class BaseApp:
    hook_cls = BaseAppHook
    store_cls = DefaultStorageHook

    def __init__(self, sess: Session, engine: AsyncEngine, conf: Settings) -> None:
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        self._get_logger(conf.log)
        self.silent_noisy_logger()
        self.fetch_lock = asyncio.Lock()

        self.engine = engine
        self.log.info('数据库已连接')

        self.loginman = LoginMan(
            sess, engine, conf.qzone.uin, conf.qzone.qr_strategy,
            conf.qzone.password.get_secret_value() if conf.qzone.password else None
        )
        self.qzone = FeedApi(sess, self.loginman)
        self.log.info('Qzone端初始化完成')

        self.updater = Updater(
            token=conf.bot.token.get_secret_value(),
            defaults=Defaults(
                parse_mode=ParseMode.HTML, run_async=False, **conf.bot.default.dict()
            ),
            request_kwargs=self._request_args(conf.bot.network),
            workers=0
        )

        block = conf.qzone.block or []
        block = block.copy()
        if conf.qzone.block_self: block.append(conf.qzone.uin)
        kw = conf.bot.dict(include={'admin', 'send_gif_as_anim'})

        self.forward = self.hook_cls(sess, self.updater.bot, block=block, **kw)
        self.forward.register_hook(self.store_cls(self.engine))
        self.loginman.register_hook(self.forward)
        self.qzone.register_hook(self.forward)
        self.log.info('TG端初始化完成')

    @property
    def bot(self):
        return self.forward.bot

    @property
    def sess(self):
        return self.qzone.api.sess

    @property
    def store(self) -> DefaultStorageHook:
        return cast(DefaultStorageHook, self.forward.hook)

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
                    if not (p := Path(e.filename).parent).exists(): p.mkdir(parents=True)
                    else: raise e
                else: break
        else:
            default = {
                'format': '[%(levelname)s] %(asctime)s %(name)s: %(message)s',
                'datefmt': '%Y %b %d %H:%M:%S',
                'level': 'INFO',
            }
            default.update(conf.dict())
            default.pop('conf', None)
            logging.basicConfig(**default)

        self.log = logging.getLogger(self.__class__.__name__)
        return self.log

    def _request_args(self, conf: NetworkConf) -> dict:
        """(internal use only) Build request_kwargs for PTB updater.

        :param conf: NetworkConf from settings.
        :return: request_kwargs
        """

        args = {}
        proxy = conf.proxy
        if proxy and str.startswith(proxy.scheme, 'socks'):
            if proxy.user:
                args['urllib3_proxy_kwargs'] = {
                    'urllib3_proxy_kwargs': proxy.user,
                    'urllib3_proxy_kwargs': proxy.password
                }
            proxy = AnyUrl.build(
                scheme=proxy.scheme,
                host=proxy.host,
                tld=proxy.tld,
                port=proxy.port,
                path=proxy.path,
                query=proxy.query,
                fragment=proxy.fragment
            )
        if proxy: args['proxy_url'] = proxy
        return args

    def silent_noisy_logger(self):
        """Silent some noisy logger in other packages."""

        if self.log.level >= logging.WARN or self.log.level == logging.DEBUG: return
        logging.getLogger("apscheduler.scheduler").setLevel(logging.WARN)
        logging.getLogger("apscheduler.executors.default").setLevel(logging.WARN)
        logging.getLogger("charset_normalizer").setLevel(logging.WARN)

    async def run(self):
        """Run the app. Current thread will be blocked until KeyboardInterrupt is raised
        or `loop.stop()` is called."""

        first_run = not await self.loginman.table_exists()
        self.log.info('注册心跳...')
        self.qzone.add_heartbeat()
        self.log.info('注册数据库清理任务...')
        self.store.add_clean_task(self.conf.bot.storage.keepdays)
        self.log.info('等待异步初始化任务...')
        qe.proxy = self.conf.bot.network.proxy and str(self.conf.bot.network.proxy)
        init_task = [qe.init(), self.store.create(), self.loginman.load_cached_cookie()]
        await asyncio.wait(init_task)

        if first_run:
            await self.license(self.conf.bot.admin)

        await anext(self.bot.send_message(self.conf.bot.admin, 'bot初始化完成，发送 /start 启动 🚀'))

        # idle
        while True:
            await asyncio.sleep(1)

    def stop(self):
        self.qzone.stop()
        self.updater.stop()

    async def fetch(self, to: Union[int, str], *, reload: bool, is_period: bool = False):
        """fetch feeds.

        :param reload: dismiss existing records in database
        :param is_period: triggered by heartbeat, defaults to False

        :raises `SystemExist`: unexcpected error
        """
        # No need to acquire lock since all fetch in BaseApp is triggered by heartbeat
        # which has 300s interval.
        # NOTE: subclass must handle async/threading lock here
        self.log.info(f"Start fetch with reload={reload}, period={is_period}")

        # start a new batch
        self.forward.new_batch()
        # fetch feed
        check_exceed = None if reload else self.store.exists
        try:
            got = await self.qzone.get_feeds_by_second(
                self.conf.qzone.dayspac * 86400, exceed_pred=check_exceed
            )
        except (UserBreak, LoginError):
            self.qzone.hb.cancel()
            self.forward.add_hook_ref('command', anext(self.bot.send_message(to, '命令已取消')))
            return

        if got == 0:
            self.forward.add_hook_ref('command', anext(self.bot.send_message(to, '您已跟上时代🎉')))
            return

        # forward
        self.forward.msg_scd.set_upper_bound(got)
        try:
            await self.qzone.wait()
            await self.forward.send_all()
        except:
            self.log.fatal('Unexpected exception in forward.send_all', exc_info=True)
            from sys import exit
            exit(1)

        # Since ForwardHook doesn't inform errors respectively, a summary of errs is sent here.
        max_retry_exceed = filter(
            lambda i: len(i) == self.forward.msg_scd.retry, self.forward.msg_scd.excs.values()
        )
        errs = len(list(max_retry_exceed))
        log_level_helper = f"\n当前日志等级为{self.log.level}, 将日志等级调整为 DEBUG 以获得完整调试信息。" if self.log.level > 10 else ''
        err_msg = f"查看服务端日志，在我们的讨论群 {DISCUSS_HTML} 寻求帮助。" + log_level_helper if errs else ''
        await anext(self.bot.send_message(to, f"发送结束，共{got}条，{errs}条错误。" + err_msg))

    async def license(self, to: ChatId):
        from telegram.parsemode import ParseMode
        async for i in self.bot.send_message(to, "用户协议", parse_mode=ParseMode.MARKDOWN_V2):
            pass
