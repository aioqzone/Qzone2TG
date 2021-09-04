import time
from utils.decorator import FloodControl
from unittest import TestCase

verbose = False


def echo(i):
    if verbose: print(i, time.time() - BASE_TIME)


def bomb(i):
    echo(i)
    raise NotImplementedError


fc30 = FloodControl(30)

class TestFlood(TestCase):
    def setUp(self) -> None:
        global BASE_TIME
        BASE_TIME = time.time()

    def testFlood(self):
        f = fc30()(echo)
        st = time.time()
        for i in range(150):
            f(i)
        self.assertGreater(time.time(), st + 4)

    def testCount(self):
        f = fc30(len)(echo)
        st = time.time()
        for i in range(0, 150, 5):
            f(list(range(i, i + 5)))
        self.assertGreater(time.time(), st + 4)

    def testExpt(self):
        f = fc30()(bomb)
        st = time.time()
        for i in range(150):
            try:
                f(i)
            except NotImplementedError:
                pass
        self.assertGreater(time.time(), st + 4)

    def testParentControl(self):
        fc = FloodControl(30)
        fe = fc()(echo)

        def callfe(i):
            return fe(i)

        fb = fc(lambda i: 2)(callfe)
        fb(0)
        self.assertEqual(fc.task_num, 2)
