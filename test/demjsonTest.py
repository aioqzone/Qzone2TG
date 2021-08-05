import json
from time import time
from unittest import TestCase

import demjson
from qzonebackend.qzone import json_loads

# testDemjson (demjsonTest.TestSpeed) ... 1.7905035018920898 s
# ok
# testRegulate (demjsonTest.TestSpeed) ... 0.011957883834838867 s
# ok


class AccTest(TestCase):
    def setUp(self):
        with open('tmp/demjson.json', encoding='utf8') as f:
            self.j = f.read()

    def testAcc(self):
        m = json_loads(self.j)
        d = demjson.decode(self.j)
        self.assertDictEqual(d, m)


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
