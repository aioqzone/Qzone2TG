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


Path('data').mkdir(exist_ok=True)
db = sqlite3.connect('data/test.db', check_same_thread=False)
spider = QzoneScraper(token_tbl=TokenTable(db.cursor()), **load_conf().qzone)


class QzoneTest(unittest.TestCase):
    def test0_UpdateStatus(self):
        try:
            spider.updateStatus()
        except LoginError:
            self.skipTest('Account banned.')

    def test1_FetchPage(self):
        feeds = spider.fetchPage(1)
        self.assertTrue(0 < len(feeds) <= 10)
        feeds.extend(spider.fetchPage(2))
        global FEEDS
        FEEDS = [QZFeedParser(i) for i in feeds]

    def test2_GetFullContent(self):
        if not FEEDS: self.skipTest('pred test failed')
        hit = False
        for i in FEEDS:
            if not i.isCut(): continue
            spider.getCompleteFeed(i.parseFeedData())
            hit = True
        if not hit: self.skipTest('no sample crawled')

    def test3_doLike(self):
        for i in FEEDS:
            if not i.isLike: spider.doLike(i.getLikeId())
            break
        else:
            self.skipTest('no sample crawled')

    def testzzzz(self):
        db.close()
