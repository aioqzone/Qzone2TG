import os

import pytest
from frontend.tg.ui import TgExtracter
from middleware.storage import FeedBase, TokenTable
from omegaconf import OmegaConf
from qzone.exceptions import LoginError
from qzone.feed import QZCachedScraper
from qzone.heartbeat import HBMgr
from qzone.scraper import QzoneScraper

db = spider = FEEDS = None


def load_conf():
    from src.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_dotlist([f'qzone.password={os.environ.get("TEST_PASSWORD")}'])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


def setup_module() -> None:
    global db, spider
    db = FeedBase('data/test.db', plugins={'tg': {'is_sent': 'BOOLEAN default 0'}})
    spider = QZCachedScraper(QzoneScraper(TokenTable(db.db), **load_conf().qzone), db)
    spider.cleanFeed()


def is_sorted(iterable, key=None):
    it = iter(iterable)
    cur = next(it)
    cur = key(cur) if key else cur
    for i in it:
        i = key(i) if key else i
        if cur > i: return False
        cur = i
    return True


def test_Fetch():
    global spider
    try:
        assert spider.getNewFeeds(1, True)
        assert spider.getNewFeeds(2, True)
    except LoginError:
        pytest.skip('Account banned.', allow_module_level=True)
    


def test_New():
    global FEEDS
    FEEDS = None
    FEEDS = db.getFeed(
        cond_sql='is_sent IS NULL OR is_sent=0',
        plugin_name='tg',
        order=True,
    )
    assert isinstance(FEEDS, list)
    assert is_sorted(FEEDS, lambda f: f.abstime)


def test_Extract():
    if FEEDS is None: pytest.skip('pred test failed.')
    for i in FEEDS:
        i = TgExtracter(i, spider.qzone.uin)
        msg, media = i.content()
        assert msg
        assert isinstance(media, list)
        for url in media:
            assert isinstance(url, str)
            assert url.startswith('http')


def teardown_module():
    db.close()
