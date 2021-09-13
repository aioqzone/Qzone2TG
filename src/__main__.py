import argparse
import logging
import sys
from getpass import getpass

import keyring
from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig
from omegaconf.listconfig import ListConfig

from __version__ import NAME, NAME_LOWER
from frontend.tg import PollingBot, RefreshBot, WebhookBot
from middleware.storage import FeedBase, TokenTable
from qzone import QzoneScraper
from qzone.feed import QZCachedScraper

DEFAULT_LOGGER_FMT = '[%(levelname)s] %(asctime)s %(name)s: %(message)s'
NO_INTERACT: bool = True


def getPassword(qzone: DictConfig):
    PWD_KEY = "password"
    strategy = qzone.get('qr_strategy', 'prefer')
    if strategy == 'force': return qzone

    if PWD_KEY in qzone:
        assert NO_INTERACT, "password can be passed by CLI only when no-interact"
        return

    pwd = keyring.get_password(NAME_LOWER, str(qzone.qq))
    if not pwd and not NO_INTERACT:
        pwd = getpass(
            f'Password{"" if strategy == "forbid" else " (press Enter to skip)"}:'
        )
        if (pwd := pwd.strip()): keyring.set_password(NAME_LOWER, str(qzone.qq), pwd)
    if not (pwd and pwd.strip()):
        d = {
            'forbid': lambda: ValueError('config: No password specified.'),
            'prefer': lambda: logging.info(
                'Password not given. qr_strategy changed from `prefer` to `force`.'
            ) or qzone.__setitem__('qr_strategy', 'force'),
            'allow': lambda: logging.warning(
                'Password not given. qr_strategy changed from `allow` to `force`.'
            ) or qzone.__setitem__('qr_strategy', 'force')
        }
        if (e := d[strategy]()): raise e
    qzone[PWD_KEY] = pwd
    return qzone


def configLogger(log_conf: DictConfig):
    if 'conf' in log_conf:
        try:
            logging.config.fileConfig(log_conf.conf)
        except FileNotFoundError as e:
            print(str(e))
    else:
        logging.basicConfig(
            format=log_conf.get('format', DEFAULT_LOGGER_FMT),
            datefmt='%Y %b %d %H:%M:%S',
            level=dict(
                CRITICAL=50,
                FATAL=50,
                ERROR=40,
                WARNING=30,
                INFO=20,
                DEBUG=10,
                NOTSET=0
            )[log_conf.get('level', 'INFO').upper()]
        )
    global logger
    logger = logging.getLogger("Main")


def configVersionControl(conf: DictConfig):
    fw = lambda msg: logger.warning("FutureWarning: " + msg)
    if isinstance(conf.bot.accept_id, ListConfig):
        fw(
            "In future versions, `bot.accept_id` is expected to be `int`. "
            "The first value of list is used now."
        )
        conf.bot.accept_id = conf.bot.accept_id[0]
    if 'interval' in conf.bot:
        fw(
            "In future versions, `bot.interval` will be replaced by `bot.daily`. "
            "Please lookup wiki for details. Current timer is set to daily (interval=86400)"
        )
        conf.bot.pop('interval')
    if 'savepwd' in conf.qzone:
        fw(
            "From 2.0.0b5, `qzone.savepwd` is deprecated. Password saving will be powered by `keyring`. "
            "Just remove this config item. "
        )

    return conf


def dueWithConfig(conf: DictConfig, NO_INTERACT=False):
    conf.setdefault('qzone', {})
    conf.setdefault('log', {})
    conf.setdefault('feed', {})

    conf = configVersionControl(conf)

    if 'qq' in conf.qzone:
        print('Login as:', conf.qzone.qq)
    elif NO_INTERACT:
        raise ValueError('config: No QQ specified.')
    else:
        conf.qzone.qq = input('QQ: ')
    getPassword(conf.qzone)
    return conf


def main(args):
    ca = OmegaConf.from_cli(args)
    cd = OmegaConf.load(CONF_PATH)
    d = OmegaConf.merge(cd, ca)

    assert 'password' not in cd.get('qzone', {}), \
    'SecurityWarning: From current version, Qzone2TG use `keyring` as password storage backend, '
    "which has been installed already. For safety reasons, please run the following command on your own:\n\n"
    "`keyring set qzone2tg {qq} {password}`\n\n"
    "Then remove `qzone.password` and `qzone.savepwd` from config file and try again.\n"
    "PS: passing password from cli is allowed."

    configLogger(d.get('log', {}))
    d = dueWithConfig(d, NO_INTERACT)
    logger.info("config loaded")

    tg_plugin_def = {'tg': {'is_sent': 'BOOLEAN default 0'}}
    db = FeedBase(f"data/{d.qzone.qq}.db", **d.feed, plugins=tg_plugin_def)
    logger.debug('database OK')

    spider = QzoneScraper(token_tbl=TokenTable(db.cursor), **d.qzone)
    feedmgr = QZCachedScraper(spider, db)
    logger.debug('crawler OK')

    method = d.bot.pop('method', None)
    if 'webhook' in d.bot:
        if method == 'polling':
            logger.warning(
                "You've specified `webhook` ConfigDict but leaving `method` as `polling`. "
                "Webhook is used in this case."
            )
        method = 'webhook'
    BotCls = {
        'polling': PollingBot,
        'webhook': WebhookBot,
        "refresh": RefreshBot
    }[method]
    bot: RefreshBot = BotCls(feedmgr=feedmgr, uin=d.qzone.qq, **d.bot)
    logger.debug('bot OK')

    spider.register_ui_hook(bot.ui)
    feedmgr.register_ui_hook(bot.ui)
    bot.run()


if __name__ == '__main__':
    psr = argparse.ArgumentParser()
    psr.add_argument(
        '-c',
        '--config',
        default="config/config.yaml",
        help='config path (*.yml;*.yaml)'
    )
    psr.add_argument(
        '--no-interaction',
        action='store_true',
        help=
        'Enter no-interaction mode: exit if any essential argument is missing instead of asking for input.'
    )
    psr.add_argument(
        '-v', '--version', action='store_true', help='print version and exit.'
    )

    arg = psr.parse_args(i for i in sys.argv if i.startswith('-'))
    if arg.version:
        from __version__ import version
        print(version())
        exit(0)
    global CONF_PATH
    CONF_PATH = arg.config
    NO_INTERACT = arg.no_interaction
    main([i for i in sys.argv[1:] if not i.startswith('-')])
