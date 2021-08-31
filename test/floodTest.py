import time
from utils.decorator import FloodControl
from unittest import TestCase


def echo(i):
    print(i, time.time() - BASE_TIME)

def bomb(i):
    echo(i)
    raise NotImplementedError

class TestFlood(TestCase):
    def setUp(self) -> None:
        global BASE_TIME
        BASE_TIME = time.time()

    def testFlood(self):
        f = FloodControl(30)(echo)
        st = time.time()
        for i in range(330):
            f(i)
        self.assertGreater(time.time(), st + 10)

    def testCount(self):
        f = FloodControl(30, len)(echo)
        st = time.time()
        for i in range(0, 330, 5):
            f(list(range(i, i + 5)))
        self.assertGreater(time.time(), st + 10)

    def testExpt(self):
        f = FloodControl(30)(bomb)
        st = time.time()
        for i in range(330):
            try:
                f(i)
            except NotImplementedError: pass
        self.assertGreater(time.time(), st + 10)
