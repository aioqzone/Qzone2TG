import unittest

from frontend.tg.ui import TgExtracter
from middleware.storage import FeedBase, TokenTable
from omegaconf import OmegaConf
from qzone import QzoneScraper
from qzone.feed import QZCachedScraper


def load_conf(args=None):
    from src.__main__ import dueWithConfig
    d = OmegaConf.load('config/test_conf.yml')
    ca = OmegaConf.from_cli(args or [])
    d = OmegaConf.merge(d, ca)
    return dueWithConfig(d, True)


db = FeedBase('data/test.db', plugins={'tg': {'is_sent': 'BOOLEAN default 0'}})
spider = QzoneScraper(token_tbl=TokenTable(db.cursor), **load_conf().qzone)
spider = QZCachedScraper(spider, db)


class FeedTest(unittest.TestCase):
    def test0_Fetch(self):
        self.assertTrue(spider.getFeedsInPage(1))
        self.assertTrue(spider.getFeedsInPage(2))

    def test1_New(self):
        global FEEDS
        FEEDS = db.getFeed(
            cond_sql='is_sent IS NULL OR is_sent=0',
            plugin_name='tg',
            order=True,
        )
        self.assertIsInstance(FEEDS, list)

    def test2_Extract(self):
        if not FEEDS: self.skipTest('pred test failed.')
        for i in FEEDS:
            i = TgExtracter(i, spider.qzone.uin)
            msg, img = i.content()
            self.assertTrue(msg)
            self.assertIsInstance(img, list)
