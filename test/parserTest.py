import re
import unittest

import yaml
from qzonebackend.qzfeedparser import QZFeedParser as Parser


class ParserTest(unittest.TestCase):
    def testTransform(self):
        with open('tmp/feeds.yaml', encoding='utf8') as f:
            feeds = yaml.safe_load_all(f)
            psrs = [Parser(i) for i in feeds]
        for i in psrs:
            with open('tmp/html/%d.html' % i.hash, 'w', encoding='utf8') as f:
                f.write(i.raw['html'])

    def testLikeData(self):
        with open('tmp/feeds.yaml', encoding='utf-8') as f:
            d = yaml.safe_load_all(f)
            d = [i for i in d if i]
            psr = Parser(d[0])
            tp = psr.parseLikeData()
            print(tp)
            self.assertTrue(len(tp) == 6)

    def testMore(self):
        with open('data/8853557023188502000.html', encoding='utf8') as f:
            psr = Parser(yaml.safe_load(f))
            self.assertTrue(psr.isCut())

    def testText(self):
        with open('tmp/feeds.yaml', encoding='utf-8') as f:
            d = yaml.safe_load_all(f)
            for i in d:
                if not i: continue
                psr = Parser(i)
                print(psr.parseText())

    def testForward(self):
        with open('tmp/raw/-6054028682261981261.yaml', encoding='utf-8') as f:
            psr = Parser(yaml.safe_load(f))
            print(psr.parseForward())
