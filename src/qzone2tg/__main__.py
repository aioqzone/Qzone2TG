import argparse
import logging
import logging.config
import sys
from getpass import getpass
from pathlib import Path

from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig

from qzone2tg import __version__ as QZ_VER
from qzone2tg.frontend.tg import PollingBot, RefreshBot, WebhookBot
from qzone2tg.middleware.storage import TokenTable
from qzone2tg.qzone.api import QzoneApi
from qzone2tg.qzone.feed import FeedDB, QzCachedScraper

NO_INTERACT: bool = True
NAME_LOWER = 'qzone2tg'


def getPassword(qzone: DictConfig):
    PWD_KEY = "password"
    strategy = qzone.get('qr_strategy', 'prefer')
    if strategy == 'force': return qzone

    if PWD_KEY in qzone and qzone[PWD_KEY]:
        if not NO_INTERACT:
            logger.fatal("只有无交互模式下才可以从 CLI 传递密码")
            exit(1)
        return qzone

    try:
        import keyring
        pwd = keyring.get_password(NAME_LOWER, str(qzone.qq))
    except ImportError:
        logger.error("keyring 未导入", exc_info=True)
        pwd = None
        keyring = None

    if not pwd and not NO_INTERACT:
        pwd = getpass(f'输入密码{"" if strategy == "forbid" else " (按回车跳过)"}:')
        if keyring and (pwd := pwd.strip()):
            try:
                keyring.set_password(NAME_LOWER, str(qzone.qq), pwd)
            except:
                logger.error('自动设置密码失败. 请您参考 wiki 手动保存密码.', exc_info=True)

    if not (pwd and pwd.strip()):
        d = {
            'forbid': lambda: ValueError('config: No password specified.'),
            'prefer': lambda: logging.info('密码未指定. qr_strategy 从 prefer 改为 force.'
                                           ) or qzone.__setitem__('qr_strategy', 'force'),
            'allow': lambda: logging.warning('密码未指定. qr_strategy 从 allow 改为 force.') or qzone.
            __setitem__('qr_strategy', 'force')
        }
        if (e := d[strategy]()): raise e

    qzone[PWD_KEY] = pwd
    return qzone


def configLogger(log_conf: DictConfig):
    global logger
    if 'conf' in log_conf and log_conf.conf and Path(log_conf.conf).exists():
        logging.config.fileConfig(log_conf.conf, disable_existing_loggers=False)
    else:
        default = {
            'format': '[%(levelname)s] %(asctime)s %(name)s: %(message)s',
            'datefmt': '%Y %b %d %H:%M:%S',
            'level': 'INFO',
        }
        default.update(log_conf)
        logging.basicConfig(**default)
    logger = logging.getLogger(NAME_LOWER + '.main')


def configVersionControl(conf: DictConfig):
    fw = lambda msg: logger.warning("FutureWarning: " + msg)

    if 'proxy' in conf.bot:
        fw("从 2.2.1b4 起, bot.proxy 重命名为 bot.network. network 配置段支持包括代理在内的更多设置. 查看 wiki 获取更多信息. ")
        conf.bot['network'] = conf.bot.pop('proxy')
    if 'auto_start' in conf.bot:
        fw("auto_start 已在多个版本中弃用. 此条目在 2.2.1b4 中移除 .")
        conf.bot.pop('auto_start')

    return conf


def dueWithConfig(conf: DictConfig, NO_INTERACT=False):
    edf = lambda: DictConfig({}, parent=conf)
    conf.setdefault('qzone', edf())
    conf.setdefault('log', edf())
    conf.setdefault('feed', edf())

    configLogger(conf.log or {})
    conf = configVersionControl(conf)

    if conf.qzone.qq:
        print('QQ:', conf.qzone.qq)
    elif NO_INTERACT:
        logger.fatal('无交互模式: QQ未指定')
        exit(1)
    else:
        conf.qzone.qq = input('QQ: ')
    getPassword(conf.qzone)
    return conf


def checkUpdate(proxy: str = None):
    from qzemoji import DBMgr
    if proxy: DBMgr.proxy = proxy
    DBMgr.autoUpdate('data/emoji.db')
    logger.debug('emoji db upgraded')

    from updater.github import GhUpdater, Repo, register_proxy
    from updater.utils import version_filter
    if proxy: register_proxy({'http': proxy, 'https': proxy})
    up = GhUpdater(Repo('JamzumSum', 'Qzone2TG'))
    vf = version_filter(up, f'>{QZ_VER}', 1, pre=True)
    vf = list(vf)
    if vf and not 'a' in vf[0].tag and not 'dev' in vf[0].tag:
        logger.info(f"Qzone2TG {vf[0].tag} availible. Current version is {QZ_VER}.")


def main(args):
    ca = OmegaConf.from_cli(args)
    cd = OmegaConf.load(CONF_PATH)
    d = OmegaConf.merge(cd, ca)

    if 'password' in cd.get('qzone', {}):
        logging.fatal(
            'Qzone2TG 使用系统keyring存储密码. 使用以下命令设置密码: \n\n'
            f"`keyring set qzone2tg {d.qzone.qq or '账号'} 密码`\n\n"
            "然后从配置文件中移除`qzone.password` 和 `qzone.savepwd` 并重启程序.\n"
            "PS: passing password from cli is allowed."
        )
        exit(1)

    d = dueWithConfig(d, NO_INTERACT)
    logger.debug(f"config loaded {d}")

    tg_plugin_def = {'tg': {'is_sent': 'BOOLEAN default 0'}}
    db = FeedDB(f"data/{d.qzone.qq}.db", **d.feed, plugins=tg_plugin_def)
    logger.debug('database OK')

    spider = QzoneApi(TokenTable(db.cursor), **d.qzone)
    feedmgr = QzCachedScraper(spider, db)
    logger.debug('crawler OK')

    checkUpdate(d.bot.get('network', {}).get('proxy_url', None))

    method = d.bot.pop('method', None)
    if 'webhook' in d.bot:
        if method == 'polling':
            logger.warning(
                "You've specified `webhook` ConfigDict but leaving `method` as `polling`. "
                "Webhook is used in this case."
            )
        method = 'webhook'
    method = method or 'polling'
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
