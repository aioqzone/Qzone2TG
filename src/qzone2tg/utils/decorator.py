import time
from collections import deque
from functools import wraps
from threading import Condition, Lock
from typing import (
    Any, Callable, Dict, Generator, List, Optional, Type, TypeVar, Union
)

from .iterutils import find_if

Exc = TypeVar('Exc', BaseException, type)
ExH = Callable[[Exc], None]
ExiH = Callable[[Exc, int], bool]
T = TypeVar('T')


def exc_chain(exc: Exc) -> Generator[Optional[Exc], Any, Any]:
    if exc == BaseException:
        yield BaseException
        return
    elif exc == object:
        raise TypeError('Not a exception')
    else:
        yield exc
        yield from exc_chain(exc.__bases__[0])


def issubclass_(ty: type, *clss: type):
    if not isinstance(ty, type): return False
    return issubclass(ty, clss)


def skip(*a, **k):
    """pass"""
    pass


def exc_handler(exc: Exc, excc: Dict[Type[Exc], Union[ExH, ExiH]]):
    ty = find_if(exc_chain(type(exc)), lambda i: i in excc)
    return ty and excc[ty]


class noexcept:
    def __init__(
        self,
        excc: Union[Dict[Exc, ExH], List[Exc], BaseException] = None,
        *,
        with_self: bool = False,
        excr: T = None,
        exit: Union[bool, int] = False
    ):
        """Pass in exception handlers and skip the exception. Else raise it.

        Args:
            excc (Union[dict[Exc, ExH], list[Exc], Exception], optional): exception handlers. Defaults to `None`.
            excd (ExH, optional): Call this whenever a exception occured, BEFORE excc is called. Defaults to `None`.
            excr (optional): return val on exception
            exit (Union[bool, int], optional): whether call `exit` when no handler matched. Defaults to False.
        """
        if excc is None: excc = {}
        if isinstance(excc, list): excc = {i: skip for i in excc}
        if issubclass_(excc, BaseException): excc = {excc: skip}
        assert isinstance(excc, dict)
        self._excc = excc
        self._wself = with_self
        self._excr = excr
        self.exit = exit

    def __call__(self, func: Callable[[Any], T]):
        @wraps(func)
        def noexcept_wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except BaseException as e:
                if (f := exc_handler(e, self._excc)): f(e)
                elif self.exit: exit(int(self.exit))
                else: raise e
                return self._excr

        return noexcept_wrapper

    def handle(self, ty: BaseException):
        def d(func: ExH):
            self._excc[ty] = func
            return func

        return d

    def add(self, ty: BaseException, func: ExH = skip):
        self._excc[ty] = func
        return self


class Retry(noexcept):
    def __init__(
        self,
        excc: Union[Dict[Exc, ExiH], List[Exc], BaseException] = None,
        times: int = 1,
        *,
        with_self=False,
        excr: T = None,
    ):
        """retry for given times and exception handlers

        Args:
            excc (Union[Dict[Exc, ExiH], List[Exc], Exception]): exception handlers. \
                if the handler return an object that `bool(o) == True`, then the loop will be broken at once, \
                with the retval as `o`.
            times (int, optional): retry times. Defaults to 1.
            with_self (bool, optional): whether call handler with self in func args. useful for methods.
            excr (optional): return val on for-else
        """
        assert times >= 0
        self._times = times
        super().__init__(excc, with_self=with_self, excr=excr)

    def __call__(self, func: Callable[[Any], T]):
        @wraps(func)
        def retry_wrapper(*args, **kwargs) -> T:
            for i in range(self._times + 1):
                try:
                    return func(*args, **kwargs)
                except BaseException as e:
                    f = exc_handler(e, self._excc)
                    if f is None: raise e
                    r = f(args[0], e, i) if self._wself else f(e, i)
                    if r: return r
            return self._excr

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


def atomic(func):
    lock = Lock()

    @wraps(func)
    def atomic(*a, **k):
        try:
            lock.acquire(True)
            return func(*a, **k)
        finally:
            lock.release()

    return atomic


class Locked():
    """NOTE: Not designed for concurency!!!"""
    _lock = False

    class _ConflictException(RuntimeError):
        pass

    def __init__(
        self,
        conflict_callback: Union[Callable[[], None], Callable[[object], None]] = None,
        *,
        with_self: bool = False
    ) -> None:
        self._on_conflict = conflict_callback
        self._wself = with_self
        self._lock = Lock()

    def __call__(self, func):
        @wraps(func)
        def lockWrapper(*args, **kwargs):
            try:
                with self:
                    return func(*args, **kwargs)
            except self._ConflictException:
                a = (kwargs.get('self', None) or args[0], ) if self._wself else ()
                return self._on_conflict and self._on_conflict(*a)

        return lockWrapper

    def lock(self):
        if not self._lock.acquire(False):
            raise self._ConflictException

    def unlock(self):
        self._lock.release()

    def __enter__(self, *a, **k):
        self.lock()

    def __exit__(self, *exc):
        self.unlock()


class Lock_RunOnce:
    """
    Run only once when racing. 
    
    Result is shared among threads. 
    Exception will be raised in every thread.
    """
    _result: Any

    def __init__(self) -> None:
        self._lock = Condition()
        self._ref = 0
        self._exc = None

    def __call__(self, func):
        @wraps(func)
        def lockWrapper(*args, **kwargs):
            with self as ref:
                if ref == 1:
                    assert not hasattr(self, '_result')
                    try:
                        self._result = func(*args, **kwargs)
                        return self._result
                    except BaseException as e:
                        self._result = e
                        self._exc = e
                        raise e
                    finally:
                        with self._lock:
                            self._lock.notify_all()
                else:
                    with self._lock:
                        self._lock.wait()
                    if self._exc: raise self._exc
                    return self._result

        return lockWrapper

    def __enter__(self):
        with self._lock:
            self._ref += 1
            return self._ref

    def __exit__(self, *exc):
        with self._lock:
            self._ref -= 1
            if self._ref == 0:
                del self._result


class cached(property):
    def __init__(self, fget: Callable, fset: Callable = None) -> None:
        super().__init__(fget, fset=fset, fdel=None)

    def __get__(self, obj: Any, type: type = None) -> Any:
        if obj is None: return self
        if not hasattr(self, '_c'):
            self._c = self.fget(obj)
        return self._c

    def __delete__(self, obj: Any) -> None:
        if hasattr(self, '_c'): del self._c

    def __set__(self, obj: Any, value: Any) -> None:
        self._c = value
        return super().__set__(obj, value)

    def setter(self, fset: Callable[[Any, Any], None]) -> property:
        return cached(fget=self.fget, fset=fset)
