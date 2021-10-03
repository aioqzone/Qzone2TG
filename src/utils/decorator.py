import time
from collections import deque
from functools import wraps
from typing import Any, Callable, Dict, Generator, Generic, List, Optional, Type, TypeVar, Union

from utils.iterutils import find_if

Exc = TypeVar('Exc', Exception, type)
ExH = Callable[[Exc], None]
ExiH = Callable[[Exc, int], bool]
DE = TypeVar('DE', Callable, callable)


def exc_chain(exc: Exc) -> Generator[Optional[Exc], Any, Any]:
    if exc == Exception:
        yield Exception
        return
    elif exc == object:
        raise TypeError('Not a exception')
    else:
        yield exc
        yield from exc_chain(exc.__bases__[0])


def bomb(e: Exc, i=0):
    raise e


def skip(e: Exc, i=0):
    pass


def exc_handler(exc: Exc, excc: Dict[Type[Exc], Union[ExH, ExiH]]):
    ty = find_if(exc_chain(type(exc)), lambda i: i in excc)
    return ty and excc[ty]


class noexcept(Generic[DE]):
    def __init__(
        self,
        excc: Union[Dict[Exc, ExH], List[Exc], Exception] = None,
        excd: ExH = None,
        exit: Union[bool, int] = False
    ):
        """Pass in exception handlers and skip the exception. Else raise it.

        Args:
            excc (Union[dict[Exc, ExH], list[Exc], Exception], optional): exception handlers. Defaults to `None`.
            excd (ExH, optional): Call this whenever a exception occured, BEFORE excc is called. Defaults to `None`.
            exit (Union[bool, int], optional): whether call `exit` when no handler matched. Defaults to False.
        """
        if isinstance(excc, list): excc = {i: skip for i in excc}
        if isinstance(excc, Exception): excc = {excc: skip}
        excc = excc or {}
        assert isinstance(excc, dict)
        self._excc = excc
        self._excd = excd
        self.exit = exit

    def __call__(self, func: DE) -> DE:
        @wraps(func)
        def noexcept_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self._excd and self._excd(e)
                if (f := exc_handler(e, self._excc)): f(e)
                elif self.exit: exit(int(self.exit))
                else: raise e

        return noexcept_wrapper


class Retry(Generic[DE]):
    def __init__(
        self,
        excc: Union[Dict[Exc, ExiH], List[Exc], Exception],
        excd: ExiH = None,
        times: int = 1,
        with_self=False,
    ):
        """retry for given times and exception handlers

        Args:
            excc (Union[Dict[Exc, ExiH], List[Exc], Exception]): exception handlers. \
                if the handler return an object that `bool(o) == True`, then the loop will be broken at once, \
                with the retval as `o`.
            excd (ExiH, optional): Call this whenever a exception occured, BEFORE excc is called. Defaults to None.
            times (int, optional): retry times. Defaults to 1.
            with_self (bool, optional): whether call handler with self in func args. useful for methods.
        """
        assert times >= 0
        if isinstance(excc, list): excc = {i: skip for i in excc}
        if isinstance(excc, Exception): excc = {excc: skip}
        excc = excc or {}
        assert isinstance(excc, dict)
        self._excc = excc
        self._excd = excd
        self._times = times
        self._wself = with_self

    def __call__(self, func):
        @wraps(func)
        def retry_wrapper(*args, **kwargs):
            for i in range(self._times + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self._excd and self._excd(e, i)
                    f = exc_handler(e, self._excc)
                    if f is None: raise e
                    r = f(args[0], e, i) if self._wself else f(e, i)
                    if r: return r

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
    def tps(self):
        return self._tps

    @tps.setter
    def tps(self, tps):
        self.reset()
        self._tps = tps

    @property
    def task_num(self) -> int:
        return sum(i[1] for i in self._ts)

    @property
    def earliest(self) -> float:
        return bool(self._ts) and self._ts[0][0]

    def wait_time(self, N) -> float:
        wait_task = self.task_num + N - self.tps
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


FT = TypeVar('FT')


class Locked(Generic[FT]):
    """NOTE: Not designed for concurency!!!"""
    _lock = False

    class _ConflictException(RuntimeError):
        pass

    def __init__(self, conflict_callback: Callable[[], None] = None) -> None:
        self._on_conflict = conflict_callback

    def __call__(self, func: FT) -> FT:
        @wraps(func)
        def lockWrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)

        return lockWrapper

    def __enter__(self, *a, **k):
        if self._lock:
            raise self._ConflictException
        self._lock = True

    def __exit__(self, ty: type, e: Exception, trace):
        if ty == self._ConflictException:
            return self._on_conflict and self._on_conflict()

        self._lock = False
        if e: raise e


class LockedMethod(Locked):
    _that = None

    def __init__(self, conflict_callback: Callable[[Any], None] = None) -> None:
        if conflict_callback: conflict_callback = lambda: conflict_callback(self._that)
        super().__init__(conflict_callback=conflict_callback)

    def __call__(self, func: FT) -> FT:
        this = self

        @wraps(func)
        def lockWrapper(self, *args, **kwargs):
            this._that = self
            with this:
                return func(self, *args, **kwargs)

        return lockWrapper
