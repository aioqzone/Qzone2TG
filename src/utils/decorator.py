from functools import wraps
import time
from typing import Any, Callable
from utils.iterutils import find_if
from collections import deque


def exc_chain(exc: type):
    if exc == Exception:
        yield Exception
        return
    elif exc == object:
        raise TypeError('Not a exception')
    else:
        yield exc
        yield from exc_chain(exc.__bases__[0])


def noexcept(excc: dict = None, *gea, **gekw):
    def noexceptDecorator(func):
        @wraps(func)
        def noexcept_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if not excc: return
                ty = find_if(exc_chain(type(e)), lambda i: i in excc)
                f = ty and excc[ty]
                if f and f(e, *gea, **gekw): return

        return noexcept_wrapper

    return noexceptDecorator


class Retry:
    def __init__(
        self,
        exc_callback: dict[type, Callable[[Exception, int], bool]],
        times: int = 1,
        inspect=False,
    ):
        assert times >= 0
        self._excc = exc_callback
        self._times = times
        self._inspect = inspect

    def __call__(self, func):
        @wraps(func)
        def retry_wrapper(*args, **kwargs):
            ecp = []
            # hook to know whether an exception is raised
            excc = {
                k: lambda e, *a, **k: ecp.append(e) or v(e, *a, **k)
                for k, v in self._excc.items()
            }
            for i in range(self._times + 1):
                f = noexcept(excc, i, *args, **kwargs)(func) if self._inspect else \
                    noexcept(excc, i)(func)
                r = f(*args, **kwargs)
                if ecp:
                    ecp.clear()
                    continue
                return r

        return retry_wrapper


class FloodControl:
    def __init__(self, times_per_second: int, epsilon=5e-2) -> None:
        self._tps = times_per_second
        self._ts = deque(maxlen=times_per_second)
        self.eps = epsilon
        self._controling = False

    @property
    def task_num(self) -> int:
        return sum(i[1] for i in self._ts)

    @property
    def earliest(self) -> float:
        return bool(self._ts) and self._ts[0][0]

    def wait_time(self, N) -> float:
        wait_task = self.task_num + N - self._tps
        if wait_task <= 0: return 0
        for i in self._ts:
            if wait_task > 0:
                wait_task -= i[1]
            if wait_task <= 0:
                return i[0] + 1 + self.eps - time.time()

    def __call__(self, pred_num_callback: Callable[[Any], int] = None):
        pred_num_callback = pred_num_callback or (lambda *a, **k: 1)

        def fcDecorator(func):
            @wraps(func)
            def fc_wrapper(*args, **kwargs):
                if self._controling: return func(*args, **kwargs)
                self._controling = True

                N = pred_num_callback(*args, **kwargs)
                while self._ts and self.earliest + 1 + self.eps < time.time():
                    self._ts.popleft()
                time.sleep(self.wait_time(N))

                try:
                    return self._run(func, N, *args, **kwargs)
                finally:
                    self._controling = False

            return fc_wrapper

        return fcDecorator

    def _run(self, func, N, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            self._ts.append((time.time(), N))


class Locked:
    """NOTE: Not used for concurency!!!"""
    _lock = False

    def __init__(self, conflict_callback=None) -> None:
        self._on_conflict = conflict_callback

    def __call__(self, func):
        @wraps(func)
        def lockWrapper(*args, **kwargs):
            if self._lock:
                return self._on_conflict and self._on_conflict()

            try:
                self._lock = True
                return func(*args, **kwargs)
            finally:
                self._lock = False

        return lockWrapper
