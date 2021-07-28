import logging

from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig

from qzonebackend.feed import QZCachedScraper
from qzonebackend.qzone import QzoneScraper
from tgfrontend.tg import PollingBot, RefreshBot, WebhookBot


def getPassword(d: DictConfig, conf_path: str):
    # getPassword w/ lasy import
    PWD_KEY = "password"
    qzone: dict = d.get('qzone')
    if qzone.get('qr_strategy', 'prefer') == 'force': return qzone

    def writePwd(pwd):
        from utils import pwdTransform
        i = OmegaConf.load(conf_path)
        i.qzone[PWD_KEY] = pwdTransform(pwd)
        i.qzone.savepwd = True
        OmegaConf.save(i, conf_path)

    if PWD_KEY in qzone:
        if not qzone[PWD_KEY].startswith('$'):
            writePwd(qzone[PWD_KEY])
        else:
            from utils import pwdTransBack
            qzone[PWD_KEY] = pwdTransBack(qzone[PWD_KEY])
    else:
        from getpass import getpass
        pwd: str = getpass('Password (press Enter to skip):')
        qzone[PWD_KEY] = pwd
        if qzone.pop('savepwd', False):
            writePwd(pwd)
    return qzone


def LoggerConf(log_conf: DictConfig):
    if 'conf' in log_conf:
        logging.config.fileConfig(log_conf.conf)
    else:
        logging.basicConfig(
            format=log_conf.get(
                'format', '[%(levelname)s] %(asctime)s %(name)s:\t%(message)s'
            ),
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


def main():
    CONF_PATH = "config/config.yaml"
    d = OmegaConf.load(CONF_PATH)
    d = OmegaConf.merge(d, OmegaConf.from_cli())

    LoggerConf(d.log or {})
    logger = logging.getLogger("Main")
    logger.info("config loaded")

    if 'qq' in d.qzone:
        print('Login as:', d.qzone.qq)
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
