import time
from functools import wraps

from apscheduler.schedulers.background import BackgroundScheduler
from utils.decorator import Locked, noexcept, skip


def setup_module():
    global sched
    sched = BackgroundScheduler({'max_instances': 4})
    sched.start()


def assert_retval(r):
    @wraps
    def d(func):
        def f(*a, **k):
            rr = func(*a, **k)
            assert r == rr
            return rr

        return f

    return d


class TestLock:
    def test_basic(self):
        i = 0

        @Locked()
        def slow():
            nonlocal i
            time.sleep(1)
            i += 1
            print(i)

        for _ in range(3):
            sched.add_job(slow, 'date')

        time.sleep(4)
        assert i == 1

    def test_callback(self):
        i = 0
        c = [0]

        @Locked(lambda: c.__setitem__(0, c[0] + 1))
        def slow():
            nonlocal i
            time.sleep(1)
            i += 1
            print(i)

        for _ in range(3):
            sched.add_job(slow, 'date')

        time.sleep(4)
        assert i == 1
        assert c[0] == 2


class TestNoexcept:
    @assert_retval(True)
    def test_basic(self):
        @noexcept(KeyboardInterrupt)
        def bomb1():
            raise KeyboardInterrupt

        @noexcept([KeyboardInterrupt])
        def bomb2():
            raise KeyboardInterrupt

        @noexcept({KeyboardInterrupt: skip})
        def bomb3():
            raise KeyboardInterrupt

        bomb1()
        bomb2()
        bomb3()
        return True

    @assert_retval(True)
    def test_callback(self):
        i = [0]

        @noexcept({KeyboardInterrupt: lambda e: i.__setitem__(0, 1)})
        def bomb1():
            raise KeyboardInterrupt

        bomb1()
        assert i[0] == 1
        return True

    @assert_retval(True)
    def test_excr(self):
        @noexcept(KeyboardInterrupt, excr=True)
        def bomb1():
            raise KeyboardInterrupt

        return bomb1()

    @assert_retval(2)
    def test_excd(self):
        i = 0

        def assert0(e):
            nonlocal i
            assert i == 0
            i = 1

        def assert1(e):
            nonlocal i
            assert i == 1
            i = 2

        @noexcept({KeyboardInterrupt: assert1}, excd=assert0)
        def bomb1():
            raise KeyboardInterrupt

        bomb1()
        return i
