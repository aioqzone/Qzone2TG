"""Base class for all app, including commands callback, etc."""
import asyncio
import logging
import logging.config
from pathlib import Path

from aiohttp import ClientSession as Session
from aioqzone.api.loginman import MixedLoginMan
from aioqzone_feed.api.feed import FeedApi
from pydantic import AnyUrl
from telegram import ParseMode
from telegram.ext import Defaults
from telegram.ext import Updater

from ..bot.hook import ForwardHook
from ..settings import BotConf
from ..settings import LogConf
from ..settings import NetworkConf
from ..settings import QzoneConf
from ..settings import Settings


class BaseApp:
    def __init__(self, sess: Session, conf: Settings) -> None:
        assert conf.bot.token
        # init logger at first
        self.conf = conf
        self._get_logger(conf.log)
        self.fetch_lock = asyncio.Lock()

        # TODO
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
            user_sig_handler=lambda signum, frame: self.qzone.stop(),
        )
        self.silent_apscheduler()
        self.forward = ForwardHook(self.updater.bot, conf.bot.admin)
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
        """Run the app. The thread will be blocked until SIGINT or stop is called."""

        self.qzone.add_heartbeat()
        await self.fetch(reload=self.conf.bot.reload_on_start)
        self.updater.idle()

    async def fetch(self, *, reload: bool, is_period: bool = False):
        """fetch feeds.

        :param reload: dismiss existing records in database
        :param is_period: triggered by heartbeat, defaults to False
        """
        # No need to acquire lock since all fetch in BaseApp is triggered by heartbeat
        # which has 300s interval.
        self.log.info(f"Start with reload={reload}, period={is_period}")
        self.forward.new_batch()
        check_exceed = None if reload else x
        got = await self.qzone.get_feeds_by_second(self.conf.qzone.dayspac * 86400, check_exceed)
        assert self.forward.msg_scd
        self.forward.msg_scd.set_upper_bound(got)
        await self.forward.msg_scd.send_all()
        errs = len(self.forward.msg_scd.excs)
        self.bot.send_message()
