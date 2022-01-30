"""A message queue for sending feeds."""

from abc import abstractmethod
import asyncio
from collections import defaultdict
import time
from typing import Awaitable, Callable, Optional

from aioqzone.interface.hook import Emittable
from aioqzone.interface.hook import Event
from aioqzone_feed.type import FeedContent


class _rsct:
    """We need this because telegram api limits bot message frequency per senconds.

    The limit includes (text) message, image message and gallery message. Thus all `send_message`,
    `send_photo`, `send_group_message` must be wrapped by this context derived from the same semaphore."""
    _start: float

    def __init__(self, lock: 'RelaxSemaphore', num: int = 1):
        self.lock = lock
        self.num = num
        self._slice = num / lock._max

    async def __aenter__(self):
        await self.lock.acquire(self.num)
        self._start = time.time()
        return None

    async def __aexit__(self, *exc):
        await asyncio.sleep(self._start + self._slice - time.time())
        self.lock.release(self.num)


class RelaxSemaphore(asyncio.Semaphore):
    _loop: asyncio.AbstractEventLoop

    def __init__(self, value: int = 30):
        self._max = value
        super().__init__(value)

    async def acquire(self, num: int = 1) -> bool:
        """Do NOT acquire from RelaxSemaphore directly.

        Example:

        >>> sem = RelaxSemaphore(30)
        >>> async with sem.num(5):  # always call with RelaxSemaphore.num
        >>>     send_gallery(...)
        """
        for i in range(num):
            await super().acquire()
        return True

    def release(self, num: int = 1) -> None:
        for i in range(num):
            super().release()

    def num(self, num: int = 1):
        return _rsct(self, num)


class ForwardEvent(Event):
    force_send_all: Callable[[], Awaitable[None]]

    @abstractmethod
    async def SendNow(self, feed: FeedContent):
        pass

    @abstractmethod
    async def FeedDroped(self, feed: FeedContent, *exc):
        pass


class MsgScheduler(Emittable):
    """Buf a batch of message and schedule them with hook."""
    hook: ForwardEvent
    __slots__ = ('buffer', 'excs', '_max', '_retry', '_point')

    def __init__(self, val: int = 0, max_retry: int = 2) -> None:
        assert max_retry > 0
        self.buffer = {}
        self.excs = defaultdict(list)
        self._max = 0
        self._retry = max_retry
        if val > 0: self.set_upper_bound(val)

    def set_upper_bound(self, val: int):
        assert val > 0
        self._max = val
        self._point = val - 1    # which feed should be sent in advance

    def register_hook(self, hook: ForwardEvent):
        hook.force_send_all = self.send_all
        return super().register_hook(hook)

    async def add(self, bid: int, feed: FeedContent):
        self.buffer[bid] = feed
        if self._max == 0: return    # skip if upper bound unknown

        for i in range(self._point, -1, -1):
            if i == self._point and self.buffer.get(i):    # if this bid should be sent
                task = self._send_pointer()
                self.buffer[self._point] = task    # feed -> task
                self._point -= 1    # donot care whether succ or not
                if self._point < 0: self._point += self._max    # count around
            else:
                break

    def _send_pointer(self):
        def check_succ(task: asyncio.Task):
            assert feed
            exc = task.exception()
            if exc:
                self.excs[pointer].append(exc)    # record exc
                if len(self.excs[pointer]) < self._retry:    # wait for retry
                    self.buffer[pointer] = feed    # task -> feed
                    return
                # drop feed with collected exceptions
                task = asyncio.create_task(self.hook.FeedDroped(feed, *self.excs[pointer]))
                task.add_done_callback(lambda _: self.buffer.__setitem__(pointer, None))
                self.buffer[pointer] = task
                return

            self.buffer[pointer] = None    # task -> None

        pointer = self._point    # ref current pointer
        feed: Optional[FeedContent] = self.buffer.get(self._point)
        if feed is None: return

        task = asyncio.create_task(self.hook.SendNow(feed))
        task.add_done_callback(check_succ)
        return task

    async def send_all(self):
        assert len(self.buffer), "Wait until all item arrive"
        while any(self.buffer.values()):
            for self._point in range(self._max - 1, -1, -1):
                o = self.buffer.get(self._point)
                if o is None: continue
                if isinstance(o, asyncio.Task):
                    task = o
                else:
                    assert isinstance(o, FeedContent)
                    task = self._send_pointer()

                assert task
                try:
                    await task
                except (SystemExit, BaseException) as e:
                    pass    # callback will handle exceptions
            await asyncio.sleep(0)    # essential for schedule tasks
