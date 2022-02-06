"""Base class for all app. Scheduled by heartbeat. No interaction with user."""

import asyncio
import logging
import logging.config
from pathlib import Path
from typing import Union

from aiohttp import ClientSession as Session
from aioqzone.api.loginman import MixedLoginMan
from aioqzone_feed.api.feed import FeedApi
from pydantic import AnyUrl
from telegram import ParseMode
from telegram.ext import Defaults
from telegram.ext import Updater

from ..settings import LogConf
from ..settings import NetworkConf
from ..settings import Settings
from .hook import BaseAppHook
from .storage import FeedStore


class BaseApp:
    hook_cls = BaseAppHook

    def __init__(self, sess: Session, conf: Settings) -> None:
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        self._get_logger(conf.log)
        self.fetch_lock = asyncio.Lock()

        self.store = FeedStore(conf.bot.storage.database)
        self.log.info('数据库已连接')

        loginman = MixedLoginMan(
            sess, conf.qzone.uin, conf.qzone.qr_strategy,
            conf.qzone.password.get_secret_value() if conf.qzone.password else None
        )
        self.qzone = FeedApi(sess, loginman)
        self.log.info('Qzone端初始化完成')

        self.updater = Updater(
            token=conf.bot.token.get_secret_value(),
            defaults=Defaults(
                parse_mode=ParseMode.HTML, run_async=True, **conf.bot.default.dict()
            ),
            request_kwargs=self._request_args(conf.bot.network),
        )
        self.silent_apscheduler()
        self.forward = self.hook_cls(self.updater.bot, conf.bot.admin)
        self.log.info('TG端初始化完成')

    @property
    def bot(self):
        return self.forward.bot

    def _get_logger(self, conf: LogConf):
        """(internal use only) Build a logger from given config.

        :param conf: conf from settings.
        :type conf: :class:`qzone2tg.settings.LogConf`
        :return: the logger
        :rtype: :obj:`logging.Logger`
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
        :type conf: :class:`qzone2tg.settings.NetworkConf`
        :return: request_kwargs
        :rtype: :obj:`dict`
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

    def silent_apscheduler(self):
        """Silent the noisy apscheduler logger."""

        if self.log.level >= logging.WARN or self.log.level == logging.DEBUG: return
        logging.getLogger("apscheduler.scheduler").setLevel(logging.WARN)
        logging.getLogger("apscheduler.executors.default").setLevel(logging.WARN)

    async def run(self):
        """Run the app. Current thread will be blocked until KeyboardInterrupt is raised
        or `loop.stop()` is called."""

        self.log.info('注册心跳')
        self.qzone.add_heartbeat()
        await self.fetch(self.conf.bot.admin, reload=self.conf.bot.reload_on_start)
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.qzone.stop()
        except:
            self.log.fatal('Uncaught Error! Exit...', exc_info=True)

    async def fetch(self, to: Union[int, str], *, reload: bool, is_period: bool = False):
        """fetch feeds.

        :param reload: dismiss existing records in database
        :param is_period: triggered by heartbeat, defaults to False
        """
        # No need to acquire lock since all fetch in BaseApp is triggered by heartbeat
        # which has 300s interval.
        # NOTE: subclass must handle async/threading lock here
        self.log.info(f"Start fetch with reload={reload}, period={is_period}")

        # start a new batch
        self.forward.new_batch()
        # fetch feed
        check_exceed = None if reload else lambda f: self.store.exists(f.fid)
        got = await self.qzone.get_feeds_by_second(
            self.conf.qzone.dayspac * 86400, exceed_pred=check_exceed
        )
        # forward
        self.forward.msg_scd.set_upper_bound(got)
        await self.forward.send_all()

        # Since ForwardHook doesn't handle errs respectively, a summary of errs is sent here.
        errs = len(self.forward.msg_scd.excs)
        if errs:
            log_level_helper = f"当前日志等级为{self.log.level}, 将日志等级调整为 DEBUG 以获得完整调试信息。" if self.log.level > 10 else ''
            self.bot.send_message(
                to, f"发送期间有{errs}条说说抛出异常。查看服务端日志，"
                "在我们的讨论群 @qzone2tg_discuss 寻求帮助。" + log_level_helper
            )
