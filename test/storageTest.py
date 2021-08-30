import yaml
from unittest import TestCase
from middleware.storage import FeedBase
from qzone.parser import QZFeedParser


class SqlTest(TestCase):
    def setUp(self):
        self.s = FeedBase(
            'data/test.db',
            plugins={
                'tg': {
                    'is_sent': 'BOOLEAN default 0'
                },
            },
            keepdays=0
        )

    def testCreate(self):
        pass

    def testInsert(self):
        with open('tmp/raw/-2582438704761084379.yaml', encoding='utf8') as f:
            feed = yaml.safe_load(f)

        feed = QZFeedParser(feed)
        self.s.dumpFeed(feed)

    def testRead(self):
        a = self.s.getFeed()
        print(a)

    def testClean(self):
        self.s.cleanFeed()
        a = self.s.getFeed()
        self.assertEqual(len(a), 0)
        self.s.cursor.execute('select * from tg')
        self.assertEqual(len(self.s.cursor.fetchall()), 0)
        a = self.s.archive['397e51599d5ef560321f0000']
        print(a)

    def testGetUnsent(self):
        a = self.s.getFeed('is_sent IS NULL OR is_sent=0', 'tg')
        print(a)
        self.assertTrue(a)
