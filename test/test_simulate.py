import os
from pathlib import Path

import pytest
from frontend.tg.ui import TgExtracter
from middleware.storage import TokenTable
from omegaconf import OmegaConf
from qzone.exceptions import LoginError
from qzone.feed import FeedDB, QZCachedScraper
from qzone.scraper import QzoneScraper

db = FEEDS = None


def conf():
    from src.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_dotlist([f'qzone.password={os.environ.get("TEST_PASSWORD")}'])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


def setup_module() -> None:
    global db
    Path('data').mkdir(exist_ok=True)
    db = FeedDB('data/test.db', plugins={'tg': {'is_sent': 'BOOLEAN default 0'}})


def is_sorted(iterable, key=None):
    it = iter(iterable)
    cur = next(it)
    cur = key(cur) if key else cur
    for i in it:
        i = key(i) if key else i
        if cur > i: return False
        cur = i
    return True


class TestHtml:
    @classmethod
    def setup_class(cls):
        p = Path('tmp/html')
        if not p.exists():
            cls.html = []
            return
        cls.html = [i for i in p.iterdir() if i.suffix == '.html']

    def testAll(self):
        from qzone.parser import QzHtmlParser
        from qzemoji import DBMgr
        DBMgr.enable_auto_update = False
        for i in self.html:
            with open(i, encoding='utf8') as f:
                p = QzHtmlParser(f.read())
                p.parseBio()
                p.parseForward()
                p.parseText()
                p.parseImage()
                p.parseVideo()


class TestSimulate:
    @classmethod
    def setup_class(cls):
        cls.spider = QZCachedScraper(
            QzoneScraper(TokenTable(db.cursor),
                         **conf().qzone), db
        )
        cls.spider.cleanFeed()

    def test_Fetch(self):
        try:
            self.spider.qzone.updateStatus()
        except LoginError:
            pytest.skip('Account banned.', allow_module_level=True)
        assert self.spider.fetchNewFeeds(no_pred=1, ignore_exist=True)

    def test_New(self):
        global FEEDS
        FEEDS = None
        FEEDS = self.spider.db.getFeed(
            cond_sql='is_sent IS NULL OR is_sent=0',
            plugin_name='tg',
            order=True,
        )
        assert isinstance(FEEDS, list)
        if FEEDS:
            assert is_sorted(FEEDS, lambda f: f.abstime)

    def test_Extract(self):
        global FEEDS
        if not FEEDS: pytest.skip('pred test failed.')
        for i in FEEDS:
            i = TgExtracter(i, self.spider.qzone.uin)
            msg, media = i.content()
            assert msg
            assert isinstance(media, list)
            for url in media:
                assert isinstance(url, str)
                assert url.startswith('http')


def teardown_module():
    db.close()
