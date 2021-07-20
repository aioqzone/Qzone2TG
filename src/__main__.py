import getpass
import logging

import yaml
from omegaconf import OmegaConf

import qzonebackend.validator.jigsaw
from qzonebackend.feed import FeedOperation
from qzonebackend.qzone import QzoneScraper
from tgfrontend.tg import PollingBot, WebhookBot
from utils import pwdTransBack, pwdTransform

logging.basicConfig(
    format='[%(levelname)s] %(asctime)s %(name)s:\t%(message)s',
    datefmt='%Y %b %d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger("Main")


def main():
    d = OmegaConf.load("config/config.yaml")
    d = OmegaConf.merge(d, OmegaConf.from_cli())
    logger.info("config loaded")

    bot = d.get("bot")
    qzone = d.get("qzone")
    feed = d.get('feed')
    selenium = d.get('selenium')

    if 'qq' in qzone:
        print('QQ to login: %s' % qzone['qq'])
    else:
        qzone['qq'] = input('QQ: ')

    if "password" in qzone:
        qzone["password"] = pwdTransBack(qzone["password"])
    else:
        pwd: str = getpass.getpass('Password (press Enter to skip):')
        if 'savepwd' in qzone and qzone.pop('savepwd'):
            qzone["password"] = pwdTransform(pwd)
            with open("config.yaml", 'w') as f:
                yaml.dump(d, f)
        qzone["password"] = pwd

    del d, pwd

    qzonebackend.validator.jigsaw.product = True

    spider = QzoneScraper(selenium_conf=selenium, **qzone)
    BotCls = {'polling': PollingBot, 'webhook': WebhookBot}[bot.pop('method')]
    bot = BotCls(feedmgr=FeedOperation(spider, **feed), **bot)
    spider.register_ui_hook(bot.ui)
    bot.run()


if __name__ == '__main__':
    main()
