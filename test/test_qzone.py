import os
import sqlite3
from pathlib import Path

import pytest
from omegaconf import OmegaConf
from qzone2tg.middleware.storage import TokenTable
from qzone2tg.qzone.exceptions import LoginError
from qzone2tg.qzone.parser import QzJsonParser
from qzone2tg.qzone.scraper import QzoneScraper

login = db = FEEDS = None


def load_conf():
    from qzone2tg.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_dotlist([f'qzone.password={os.environ.get("TEST_PASSWORD")}'])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


def setup_module():
    global db
    Path('data').mkdir(exist_ok=True)
    db = sqlite3.connect('data/test.db', check_same_thread=False)


class TestQzone:
    @classmethod
    def setup_class(cls):
        cls.spider = QzoneScraper(TokenTable(db.cursor()), **load_conf().qzone)

    def test_UpdateStatus(self, force_login=True):
        global login
        try:
            self.spider.updateStatus(force_login=force_login)
            login = True
        except LoginError:
            login = False
            pytest.skip('Account banned.', allow_module_level=True)

    def test_checkUpdate(self):
        if login is None: self.test_UpdateStatus(False)
        if login == False: pytest.skip('not login', allow_module_level=True)
        self.spider.checkUpdate()

    def test_FetchPage(self):
        if login is None: self.test_UpdateStatus(False)
        if login == False: pytest.skip('not login', allow_module_level=True)
        global FEEDS
        feeds = self.spider.fetchPage(1, 1)
        assert feeds is not None
        assert 0 < len(feeds) <= 10
        feeds.extend(self.spider.fetchPage(2))
        FEEDS = [QzJsonParser(i) for i in feeds]

    # def test_msgDetail(self):
    #     for i in FEEDS:
    #         self.spider.getFeedDetail(i.uin, i.fid)

    def test_GetFullContent(self):
        if FEEDS is None: pytest.skip('pred test failed.')
        hit = False
        for i in FEEDS:
            if not i.isCut(): continue
            self.spider.getCompleteFeed(i.feedData)
            hit = True
        if not hit: pytest.skip('no sample crawled')

    def test_doLike(self):
        if FEEDS is None: pytest.skip('pred test failed.')
        if not FEEDS: pytest.skip('pred test failed')
        for i in FEEDS:
            d = i.getLikeId()
            if i.isLike:
                assert self.spider.doLike(d, False)
                assert self.spider.doLike(d, True)
            else:
                assert self.spider.doLike(d, True)
                assert self.spider.doLike(d, False)
            return
        else:
            pytest.skip('no sample crawled')

    def test_stop(self):
        self.spider.stop()


def teardown_module() -> None:
    global db
    return db.close()
