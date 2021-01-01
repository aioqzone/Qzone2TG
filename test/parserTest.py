from qzonebackend.htmlparser import HTMLParser
import unittest
import re

class ParserTest(unittest.TestCase):
    def testIsLike(self):
        with open("tmp/test.html", encoding="utf-8") as f:
            psr = HTMLParser(f)
            r = psr.isLike()
            print(r)