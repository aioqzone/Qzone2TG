import argparse
import logging
import logging.config
import sys
from getpass import getpass

from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig
from omegaconf.listconfig import ListConfig

from qzone2tg.frontend.tg import PollingBot, RefreshBot, WebhookBot
from qzone2tg.middleware.storage import TokenTable
from qzone2tg.qzone.feed import FeedDB, QzCachedScraper
from qzone2tg.qzone.scraper import QzoneScraper

DEFAULT_LOGGER_FMT = '[%(levelname)s] %(asctime)s %(name)s: %(message)s'
NO_INTERACT: bool = True
NAME_LOWER = 'qzone2tg'


def getPassword(qzone: DictConfig):
    PWD_KEY = "password"
    strategy = qzone.get('qr_strategy', 'prefer')
    if strategy == 'force': return qzone

    if PWD_KEY in qzone:
        assert NO_INTERACT, "password can be passed by CLI only when no-interact"
        return

    try:
        import keyring
        pwd = keyring.get_password(NAME_LOWER, str(qzone.qq))
    except ImportError:
        pwd = None

    if not pwd and not NO_INTERACT:
        pwd = getpass(f'输入密码{"" if strategy == "forbid" else " (按回车跳过)"}:')
        if (pwd := pwd.strip()): keyring.set_password(NAME_LOWER, str(qzone.qq), pwd)
    if not (pwd and pwd.strip()):
        d = {
            'forbid': lambda: ValueError('config: No password specified.'),
            'prefer': lambda: logging.info('密码未指定. qr_strategy 从 `prefer` 改为 `force`.'
                                           ) or qzone.__setitem__('qr_strategy', 'force'),
            'allow': lambda: logging.warning('密码未指定. qr_strategy 从 `allow` 改为 `force`.') or qzone.
            __setitem__('qr_strategy', 'force')
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
            level=dict(CRITICAL=50, FATAL=50, ERROR=40, WARNING=30, INFO=20, DEBUG=10,
                       NOTSET=0)[log_conf.get('level', 'INFO').upper()]
        )
    global logger
    logger = logging.getLogger("Main")


def configVersionControl(conf: DictConfig):
    fw = lambda msg: logger.warning("FutureWarning: " + msg)
    if isinstance(conf.bot.accept_id, ListConfig):
        fw("在未来的版本中, `bot.accept_id`被视为 `int`. 只有列表中的第一个值生效.")
        conf.bot.accept_id = conf.bot.accept_id[0]
    if 'proxy' in conf.bot:
        fw("从`2.2.1b4`起, `bot.proxy`重命名为`bot.network`. `network`配置段支持包括代理在内的更多设置. 查看wiki获取更多信息. ")
        conf.bot['network'] = conf.bot.pop('proxy')
    if 'auto_start' in conf.bot:
        fw("`auto_start`已在多个版本中弃用. 此条目在`2.2.1b4`中移除 .")
        conf.bot.pop('auto_start')

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


def checkUpdate():
    from qzemoji import DBMgr
    DBMgr.autoUpdate('data/emoji.db')
    logger.debug('emoji db upgraded')


def main(args):
    ca = OmegaConf.from_cli(args)
    cd = OmegaConf.load(CONF_PATH)
    d = OmegaConf.merge(cd, ca)
    configLogger(d.get('log', {}))

    if 'password' in cd.get('qzone', {}):
        logger.fatal(
            'Qzone2TG 使用系统keyring存储密码. 使用以下命令设置密码: \n\n'
            f"`keyring set qzone2tg {d.qzone.qq} 密码`\n\n"
            "然后从配置文件中移除`qzone.password` 和 `qzone.savepwd` 并重启程序.\n"
            "PS: passing password from cli is allowed."
        )
        exit(1)

    d = dueWithConfig(d, NO_INTERACT)
    logger.debug("config loaded")

    tg_plugin_def = {'tg': {'is_sent': 'BOOLEAN default 0'}}
    db = FeedDB(f"data/{d.qzone.qq}.db", **d.feed, plugins=tg_plugin_def)
    logger.debug('database OK')

    spider = QzoneScraper(TokenTable(db.cursor), **d.qzone)
    feedmgr = QzCachedScraper(spider, db)
    logger.debug('crawler OK')

    checkUpdate()

    method = d.bot.pop('method', None)
    if 'webhook' in d.bot:
        if method == 'polling':
            logger.warning(
                "You've specified `webhook` ConfigDict but leaving `method` as `polling`. "
                "Webhook is used in this case."
            )
        method = 'webhook'
    BotCls = {'polling': PollingBot, 'webhook': WebhookBot, "refresh": RefreshBot}[method]
    bot: RefreshBot = BotCls(feedmgr=feedmgr, **d.bot)
    bot.addBlockUin(d.qzone.qq)
    logger.debug('bot OK')

    feedmgr.register_ui_hook(bot.ui)
    bot.run()


if __name__ == '__main__':
    psr = argparse.ArgumentParser()
    psr.add_argument(
        '-c', '--config', default="config/config.yaml", help='config path (*.yml;*.yaml)'
    )
    psr.add_argument('--no-interaction', action='store_true', help='无交互模式: 关键配置缺失时不请求输入, 直接停止运行.')
    psr.add_argument('-v', '--version', action='store_true', help='输出版本并退出.')

    arg = psr.parse_args(i for i in sys.argv if i.startswith('-'))
    if arg.version:
        from . import __version__
        print(__version__)
        exit(0)
    global CONF_PATH
    CONF_PATH = arg.config
    NO_INTERACT = arg.no_interaction
    main([i for i in sys.argv[1:] if not i.startswith('-')])
