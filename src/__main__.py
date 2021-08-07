import logging

from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig

from qzonebackend.feed import QZCachedScraper
from qzonebackend.qzone import QzoneScraper
from tgfrontend.tg import PollingBot, RefreshBot, WebhookBot

NO_INTERACT = False
DEFAULT_LOGGER_FMT = '[%(levelname)s] %(asctime)s %(name)s:\t%(message)s'


def getPassword(d: DictConfig, conf_path: str):
    # getPassword w/ lasy import
    PWD_KEY = "password"
    qzone: dict = d.get('qzone')
    if (strategy := qzone.get('qr_strategy', 'prefer')) == 'force': return qzone

    def writePwd(pwd):
        from utils import pwdTransform
        i = OmegaConf.load(conf_path)
        i.qzone[PWD_KEY] = pwdTransform(pwd)
        i.qzone.savepwd = True
        OmegaConf.save(i, conf_path)

    if PWD_KEY in qzone:
        qzone.pop('savepwd', None)
        if not qzone[PWD_KEY].startswith('$'):
            writePwd(qzone[PWD_KEY])
        else:
            from utils import pwdTransBack
            qzone[PWD_KEY] = pwdTransBack(qzone[PWD_KEY])
    else:
        from getpass import getpass
        pwd = '' if NO_INTERACT else getpass('Password (press Enter to skip):')
        if strategy == 'forbid' and not pwd.strip():
            raise ValueError('config: No password specified.')
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


def main():
    ca = OmegaConf.from_cli()
    CONF_PATH = ca.pop('--config', None) or "config/config.yaml"
    global NO_INTERACT 
    if '--no-interaction' in ca: 
        NO_INTERACT = True
        ca.pop('--no-interaction')

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
    bot: RefreshBot = BotCls(feedmgr=feedmgr, **d.bot)
    spider.register_ui_hook(bot.ui)
    feedmgr.register_ui_hook(bot.ui)
    bot.run()


if __name__ == '__main__':
    main()
