import re
import unittest

import demjson
import yaml
from qzonebackend.htmlparser import HTMLParser


class ParserTest(unittest.TestCase):
    def testIsLike(self):
        with open("tmp/test.html", encoding="utf-8") as f:
            psr = HTMLParser(f)
            r = psr.isLike()
            print(r)

    def testTransform(self):
        htmls = None
        with open('tmp/feeds.yaml', encoding='utf8') as f:
            feeds = yaml.load_all(f)
            htmls = [i['html'] for i in feeds if i['appid'] == '311']
        for i in htmls:
            with open('tmp/html/%d.html' % hash(i), 'w', encoding='utf8') as f:
                f.write(i)
