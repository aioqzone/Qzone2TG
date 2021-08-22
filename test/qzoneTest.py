import unittest

import yaml
from qzone import QzoneScraper
from utils.encrypt import pwdTransBack


def load_conf():
    with open('config/config.yaml') as f:
        d = yaml.safe_load(f)
        q: dict = d['qzone']
        if 'savepwd' in q: q.pop('savepwd')
        return q


class WalkerTest(unittest.TestCase):
    def setUp(self):
        import cv2 as cv
        import numpy as np
        from middleware.uihook import NullUI
        q = load_conf()
        self.spider = QzoneScraper(**q)

        class UI(NullUI):
            def QrFetched(self, png: bytes):
                img = cv.imdecode(
                    np.asarray(bytearray(png), dtype='uint8'), cv.IMREAD_COLOR
                )
                cv.imshow('qrcode', img)
                cv.waitKey()

        self.spider.register_ui_hook(UI())

    def testLogin(self):
        cookie = self.spider.login()
        self.assertIsNotNone(cookie)


class QzoneTest(unittest.TestCase):
    def setUp(self):
        q = load_conf()
        self.spider = QzoneScraper(**q)
        from middleware.uihook import NullUI

        class UI(NullUI):
            def QrFetched(self, png: bytes):
                import cv2 as cv
                import numpy as np
                img = cv.imdecode(
                    np.asarray(bytearray(png), dtype='uint8'), cv.IMREAD_COLOR
                )
                cv.imshow('qrcode', img)
                cv.waitKey()

        self.spider.register_ui_hook(UI())

    def testFetchPage(self):
        feeds = self.spider.fetchPage(1)
        self.assertTrue(0 < len(feeds) <= 10)
        with open('tmp/feeds.yaml', 'w', encoding='utf8') as f:
            yaml.dump_all(feeds, f)

    def testGetFullContent(self):
        self.spider.updateStatus()
        feed = self.spider.fetchPage(1)[0]
        html = self.spider.getCompleteFeed(feed["html"])
        print(html)
