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

class QzoneTest(unittest.TestCase):
    def setUp(self):
        with open('config/config.yaml') as f:
            d: dict = yaml.safe_load(f)['qzone']
            pwd = pwdTransBack(d.pop('password'))
            self.spider = QzoneScraper(**d, password=pwd)

    def testGetFullContent(self):
        self.spider.updateStatus(force_login=True)
        feed = self.spider.get_content(1)[0]
        html = self.spider.getFullContent(feed["html"])
        print(html)