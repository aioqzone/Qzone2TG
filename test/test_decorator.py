import time
from functools import wraps

from concurrent.futures import ThreadPoolExecutor

from utils.decorator import Lock_RunOnce, Locked, noexcept, skip


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
    @classmethod
    def setup_class(cls):
        from apscheduler.schedulers.background import BackgroundScheduler
        cls.sched = BackgroundScheduler({'max_instances': 4})
        cls.sched.start()

    def test_basic(self):
        i = 0

        @Locked()
        def slow():
            nonlocal i
            time.sleep(1)
            i += 1
            print(i)

        for _ in range(3):
            self.sched.add_job(slow, 'date')

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
            self.sched.add_job(slow, 'date')

        time.sleep(4)
        assert i == 1
        assert c[0] == 2


class TestLockOnce:
    @classmethod
    def setup_class(cls):
        cls.executor = ThreadPoolExecutor(2)

    def test_basic(self):
        i = 0

        @Lock_RunOnce()
        def once(_):
            time.sleep(1)
            nonlocal i
            i += 1
            return i

        a, b = self.executor.map(once, [0] * 2)
        assert a == b == 1


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
