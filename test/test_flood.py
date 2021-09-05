import time
from utils.decorator import FloodControl

verbose = False


def echo(i):
    if verbose: print(i, time.time() - BASE_TIME)


def bomb(i):
    echo(i)
    raise NotImplementedError


fc30 = FloodControl(30)


class TestFlood:
    def setup(self) -> None:
        global BASE_TIME
        BASE_TIME = time.time()
        fc30.reset()

    def testFlood(self):
        f = fc30()(echo)
        for i in range(30):
            f(i)
        st = time.time()
        f(i)
        assert time.time() > st + 1

    def testCount(self):
        f = fc30(len)(echo)
        f(list(range(30)))
        st = time.time()
        f([0])
        assert time.time() > st + 1

    def testExpt(self):
        f = fc30()(bomb)
        for i in range(30):
            try:
                f(i)
            except NotImplementedError:
                pass
        st = time.time()
        try:
            f(i)
        except NotImplementedError:
            pass
        assert time.time() > st + 1

    def testParentControl(self):
        fc = FloodControl(30)
        fe = fc()(echo)

        def callfe(i):
            return fe(i)

        fb = fc(lambda i: 2)(callfe)
        fb(0)
        assert fc.task_num == 2
