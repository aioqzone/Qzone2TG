from qzonebackend.qzone import QzoneScraper
from utils import pwdTransBack
import yaml
import unittest


def load_conf():
    with open('config/config.yaml') as f:
        d = yaml.safe_load(f)
        q: dict = d['qzone']
        s = d['selenium']
        if 'savepwd' in q: q.pop('savepwd')
        return q, s


class WalkerTest(unittest.TestCase):
    def setUp(self):
        import cv2 as cv, numpy as np
        from urllib.request import urlopen
        q, s = load_conf()
        self.spider = QzoneScraper(selenium_conf=s, **q)

        def showurl(url):
            img = cv.imread(url)
            cv.imshow('qrcode', img)
            cv.waitKey()

        self.spider.register_ui_hook(showurl)

    def testLogin(self):
        cookie = self.spider.login()
        self.assertIsNotNone(cookie)


class QzoneTest(unittest.TestCase):
    def setUp(self):
        q, pwd, s = load_conf()
        self.spider = QzoneScraper(selenium_conf=s, password=pwd, **q)

    def testFetchPage(self):
        self.spider.updateStatus()
        feeds = self.spider.fetchPage(1)
        self.assertTrue(0 < len(feeds) <= 10)
        with open('tmp/feeds.yaml', 'w', encoding='utf8') as f:
            yaml.dump_all(feeds, f)

    def testGetFullContent(self):
        self.spider.updateStatus()
        feed = self.spider.fetchPage(1)[0]
        html = self.spider.getCompleteFeed(feed["html"])
        print(html)
