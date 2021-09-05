import os
import unittest

from frontend.tg.ui import TgExtracter
from middleware.storage import FeedBase, TokenTable
from omegaconf import OmegaConf
from qzone import QzoneScraper
from qzone.exceptions import LoginError
from qzone.feed import QZCachedScraper


def load_conf():
    from src.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_dotlist([f'qzone.password={os.environ.get("TEST_PASSWORD")}'])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


class FeedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db = FeedBase(
            'data/test.db', plugins={'tg': {
                'is_sent': 'BOOLEAN default 0'
            }}
        )
        spider = QzoneScraper(token_tbl=TokenTable(cls.db.cursor), **load_conf().qzone)
        cls.spider = QZCachedScraper(spider, cls.db)

    def test0_Fetch(self):
        try:
            self.spider.qzone.updateStatus()
            self.login = True
        except LoginError:
            self.login = False
            self.skipTest('Account banned.')
        self.assertTrue(self.spider.getFeedsInPage(1))
        self.assertTrue(self.spider.getFeedsInPage(2))

    def test1_New(self):
        if not self.login: self.skipTest('pred test failed.')
        global FEEDS
        FEEDS = self.db.getFeed(
            cond_sql='is_sent IS NULL OR is_sent=0',
            plugin_name='tg',
            order=True,
        )
        self.assertIsInstance(FEEDS, list)

    def test2_Extract(self):
        if not FEEDS: self.skipTest('pred test failed.')
        for i in FEEDS:
            i = TgExtracter(i, self.spider.qzone.uin)
            msg, img = i.content()
            self.assertTrue(msg)
            self.assertIsInstance(img, list)

    def testzzzz(self):
        self.db.close()
