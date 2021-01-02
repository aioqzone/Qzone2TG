from qzonebackend.qzone import QzoneScraper
from utils import pwdTransBack
import yaml
import unittest

class WalkerTest(unittest.TestCase):
    def setUp(self):
        with open('config/config.yaml') as f:
            d: dict = yaml.safe_load(f)['qzone']
            pwd = pwdTransBack(d.pop('password'))
            self.spider = QzoneScraper(**d, password=pwd)

    def testLogin(self):
        cookie = self.spider.login()
        self.assertIsNotNone(cookie)

class QzoneTest(unittest.TestCase):
    def setUp(self):
        with open('config/config.yaml') as f:
            d = yaml.safe_load(f)
            q: dict = d['qzone']
            s = d['selenium']
            pwd = pwdTransBack(q.pop('password'))
            self.spider = QzoneScraper(selenium_conf=s, password=pwd, **q)

    def testFetchPage(self):
        self.spider.updateStatus()
        feeds = self.spider.fetchPage(1)
        with open('tmp/feeds.yaml', 'w', encoding='utf8') as f:
            yaml.dump_all(feeds, f)

    def testGetFullContent(self):
        self.spider.updateStatus()
        feed = self.spider.fetchPage(1)[0]
        html = self.spider.getCompleteFeed(feed["html"])
        print(html)