import argparse
import logging
import sys

from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig

from frontend.tg import PollingBot, RefreshBot, WebhookBot
from qzone import QzoneScraper
from qzone.feed import QZCachedScraper

DEFAULT_LOGGER_FMT = '[%(levelname)s] %(asctime)s %(name)s:\t%(message)s'


def getPassword(d: DictConfig, conf_path: str):
    """getPassword w/ lasy import"""
    PWD_KEY = "password"
    qzone: dict = d.get('qzone')
    if (strategy := qzone.get('qr_strategy', 'prefer')) == 'force': return qzone

    def writePwd(pwd):
        from utils.encrypt import pwdTransform
        i = OmegaConf.load(conf_path)
        i.qzone[PWD_KEY] = pwdTransform(pwd)
        i.qzone.savepwd = True
        OmegaConf.save(i, conf_path)

    if PWD_KEY in qzone:
        qzone.pop('savepwd', None)
        if not qzone[PWD_KEY].startswith('$'):
            writePwd(qzone[PWD_KEY])
        else:
            from utils.encrypt import pwdTransBack
            qzone[PWD_KEY] = pwdTransBack(qzone[PWD_KEY])
    else:
        from getpass import getpass
        pwd = '' if NO_INTERACT else getpass(
            f'Password{"" if strategy == "forbid" else " (press Enter to skip)"}:'
        )
        if not pwd.strip():
            if strategy == 'forbid':
                raise ValueError('config: No password specified.')
            elif strategy == 'prefer':
                logging.info(
                    'Password not given. qr_strategy changed from `prefer` to `force`.'
                )
                qzone.qr_strategy = 'force'
            elif strategy == 'allow':
                logging.warning(
                    'Password not given. qr_strategy changed from `allow` to `force`.'
                )
                qzone.qr_strategy = 'force'
        qzone[PWD_KEY] = pwd
        if qzone.pop('savepwd', False):
            writePwd(pwd)
    return qzone


def LoggerConf(log_conf: DictConfig):
    if 'conf' in log_conf:
        try:
            logging.config.fileConfig(log_conf.conf)
        except FileNotFoundError as e:
            print(str(e))
        else:
            return

    logging.basicConfig(
        format=log_conf.get('format', DEFAULT_LOGGER_FMT),
        datefmt='%Y %b %d %H:%M:%S',
        level=dict(
            CRITICAL=50, FATAL=50, ERROR=40, WARNING=30, INFO=20, DEBUG=10, NOTSET=0
        )[log_conf.get('level', 'INFO').upper()]
    )


def main(args):
    ca = OmegaConf.from_cli(args)
    d = OmegaConf.load(CONF_PATH)
    d = OmegaConf.merge(d, ca)

    LoggerConf(d.log or {})
    logger = logging.getLogger("Main")
    logger.info("config loaded")

    if 'qq' in d.qzone:
        print('Login as:', d.qzone.qq)
    elif NO_INTERACT:
        raise ValueError('config: No QQ specified.')
    else:
        d.qzone['qq'] = input('QQ: ')
    getPassword(d, CONF_PATH)

    spider = QzoneScraper(**d.qzone)
    feedmgr = QZCachedScraper(spider, **d.feed)
    BotCls = {
        'polling': PollingBot,
        'webhook': WebhookBot,
        "refresh": RefreshBot
    }[d.bot.pop('method')]
    bot: RefreshBot = BotCls(feedmgr=feedmgr, uin=d.qzone.qq, **d.bot)
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

    arg = psr.parse_args(i for i in sys.argv if i.startswith('-'))
    global CONF_PATH, NO_INTERACT
    CONF_PATH = arg.config
    NO_INTERACT = arg.no_interaction
    main([i for i in sys.argv[1:] if not i.startswith('-')])
