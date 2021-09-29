from functools import wraps
import time
from typing import Any, Callable, Dict, Type
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


def exc_handler(exc: Exception, excc: Dict[Type[Exception], Callable]):
    ty = find_if(exc_chain(type(exc)), lambda i: i in excc)
    return ty and excc[ty]


def noexcept(excc: dict = None, excd: Callable = None):
    def noexceptDecorator(func):
        @wraps(func)
        def noexcept_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                excd and excd(e)
                if excc: exc_handler(e, excc)(e)

        return noexcept_wrapper

    return noexceptDecorator


class Retry:
    def __init__(
        self,
        exc_callback: Dict[type, Callable[[Exception, int], bool]],
        exc_default: Callable = None,
        times: int = 1,
        inspect=False,
    ):
        assert times >= 0
        self._excc = exc_callback
        self._excd = exc_default
        self._times = times
        self._inspect = inspect

    def __call__(self, func):
        @wraps(func)
        def retry_wrapper(*args, **kwargs):
            for i in range(self._times + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self._excd and self._excd(e, i)
                    if self._excc:
                        f = exc_handler(e, self._excc)
                        if not f: raise e
                        r = f(e, i, *args, **kwargs) if self._inspect else f(e, i)
                        if r: return r
                    else:
                        raise e

        return retry_wrapper


class FloodControl:
    def __init__(self, times_per_second: int, epsilon=5e-2) -> None:
        self._tps = times_per_second
        self._ts = deque(maxlen=times_per_second)
        self.eps = epsilon
        self._controling = False

    def reset(self):
        assert not self._controling
        self._ts.clear()

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
