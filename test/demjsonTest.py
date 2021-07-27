import json
from time import time
from unittest import TestCase

import demjson
from qzonebackend.qzone import json_loads
"""
testDemjson (demjsonTest.TestSpeed) ... 2.585096836090088 s
ok
testRegulate (demjsonTest.TestSpeed) ... 0.49105286598205566 s
ok
"""


class TestSpeed(TestCase):
    def setUp(self):
        with open('tmp/demjson.json', encoding='utf8') as f:
            self.j = f.read()

    def testDemjson(self):
        t = time()
        self.assertTrue(demjson.decode(self.j))
        t -= time()
        print(-t, 's')

    def testRegulate(self):
        t = time()
        self.assertTrue(json_loads(self.j))
        t -= time()
        print(-t, 's')
