import re
import unittest

import yaml
from qzonebackend.qzfeedparser import QZFeedParser as Parser


class ParserTest(unittest.TestCase):
    def testTransform(self):
        htmls = None
        with open('tmp/feeds.yaml', encoding='utf8') as f:
            feeds = yaml.safe_load_all(f)
            htmls = [i['html'] for i in feeds]
        for i in htmls:
            with open('tmp/html/%d.html' % hash(i), 'w', encoding='utf8') as f:
                f.write(i)

    def testLikeData(self):
        with open('data/-217964352468340141.html', encoding='utf-8') as f:
            psr = Parser(yaml.safe_load(f))
            tp = psr.parseLikeData()
            print(tp)
            self.assertTrue(len(tp) == 5)

    def testMore(self):
        with open('data/8853557023188502000.html', encoding='utf8') as f:
            psr = Parser(yaml.safe_load(f))
            self.assertTrue(psr.isCut())

    def testText(self):
        with open('data/458973857/18805/-7284886418583810128.yaml',
                  encoding='utf8') as f:
            psr = Parser(yaml.safe_load(f))
            print(psr.parseText())

    def testForward(self):
        with open('tmp/raw/-6054028682261981261.yaml', encoding='utf-8') as f:
            psr = Parser(yaml.safe_load(f))
            print(psr.parseForward())
