import os
from pathlib import Path
import sqlite3
import unittest

from middleware.storage import TokenTable
from omegaconf import OmegaConf
from qzone import QzoneScraper
from qzone.exceptions import LoginError
from qzone.parser import QZFeedParser


def load_conf():
    from src.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_dotlist([f'qzone.password={os.environ.get("TEST_PASSWORD")}'])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


class QzoneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path('data').mkdir(exist_ok=True)
        cls.db = sqlite3.connect('data/test.db', check_same_thread=False)
        cls.spider = QzoneScraper(
            token_tbl=TokenTable(cls.db.cursor()), **load_conf().qzone
        )

    def test0_UpdateStatus(self):
        try:
            self.spider.updateStatus()
            self.login = True
        except LoginError:
            self.skipTest('Account banned.')
            self.login = False

    def test1_FetchPage(self):
        if not self.login: self.skipTest('pred test failed')
        feeds = self.spider.fetchPage(1)
        self.assertIsNotNone(feeds)
        self.assertTrue(0 < len(feeds) <= 10)
        feeds.extend(self.spider.fetchPage(2))
        self.FEEDS = [QZFeedParser(i) for i in feeds]

    def test2_GetFullContent(self):
        if not self.FEEDS: self.skipTest('pred test failed')
        hit = False
        for i in self.FEEDS:
            if not i.isCut(): continue
            self.spider.getCompleteFeed(i.parseFeedData())
            hit = True
        if not hit: self.skipTest('no sample crawled')

    def test3_doLike(self):
        if not self.FEEDS: self.skipTest('pred test failed')
        for i in self.FEEDS:
            if not i.isLike: self.spider.doLike(i.getLikeId())
            break
        else:
            self.skipTest('no sample crawled')

    @classmethod
    def tearDownClass(cls) -> None:
        return cls.db.close()
