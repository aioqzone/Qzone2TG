"""A message queue for sending feeds."""

from abc import abstractmethod
import asyncio
from collections import defaultdict
import time
from typing import Awaitable, Callable, Optional, Union

from aioqzone.interface.hook import Emittable
from aioqzone.interface.hook import Event
from aioqzone_feed.type import FeedContent

from ..utils.iter import empty


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
    async def SendNow(self, feed: FeedContent):
        pass

    async def FeedDroped(self, feed: FeedContent, *exc):
        pass


class MsgBarrier(Emittable[ForwardEvent]):
    buffer: set[FeedContent]
    excs: dict[FeedContent, list[BaseException]]
    __slots__ = ('buffer', 'excs', '_retry')

    def __init__(self, max_retry: int = 2) -> None:
        super().__init__()
        self.buffer = set()
        self.excs = defaultdict(list)
        self._retry = max_retry

    def send_all(self):
        while self.buffer:
            feed = self.buffer.pop()
            task = self.add_hook_ref('send', self.hook.SendNow(feed))
            self._add_handler(task, feed)

    def _add_handler(self, task: asyncio.Task, feed: FeedContent):
        def check_succ(t: asyncio.Task):
            if (exc := t.exception()) is None: return    # task has been removed by add_hook_ref
            self.excs[feed].append(exc)
            if len(self.excs[feed]) < self._retry:
                task = self.add_hook_ref('send', self.hook.SendNow(feed))
                self._add_handler(task, feed)
                return
            self.add_hook_ref('hook', self.hook.FeedDroped(feed, *self.excs[feed]))

        task.add_done_callback(check_succ)
        return task


class MsgScheduler(MsgBarrier):
    """Buf a batch of message and schedule them with hook."""
    buffer: dict[int, Optional[FeedContent]]
    __slots__ = ('_max', '_point')

    def __init__(self, val: int = 0, max_retry: int = 2) -> None:
        assert max_retry >= 0
        super().__init__(max_retry)
        self.buffer = {}
        self._max = 0
        self._retry = max_retry
        if val > 0: self.set_upper_bound(val)

    def set_upper_bound(self, val: int):
        assert val > 0
        self._max = val
        self._point = val - 1    # which feed should be sent in advance

    def pending_feeds(self, reverse: bool = True):
        if not reverse: return filter(None, self.buffer.values())
        it = sorted(self.buffer.items(), key=lambda t: t[0], reverse=True)
        return filter(None, (i[1] for i in it))

    def pending_tasks(self):
        return self._tasks['send']

    def add(self, bid: int, feed: FeedContent):
        self.buffer[bid] = feed
        if self._max == 0: return    # skip if upper bound unknown

        for i in range(self._point, -1, -1):
            if i == self._point and (f := self.buffer.get(i)):    # if this bid should be sent
                self.buffer[self._point] = None    # feed -> None
                task = self.add_hook_ref('send', self.hook.SendNow(f))
                task = self._add_handler(task, f)
                self._point -= 1    # donot care whether succ or not
                if self._point < 0: self._point += self._max    # count around
            else:
                break

    async def send_all(self):
        assert len(self.buffer), "Wait until all item arrive"
        await self.wait('send')
        for feed in self.pending_feeds(reverse=True):
            task = self.add_hook_ref('send', self.hook.SendNow(feed))
            self._add_handler(task, feed)
            try:
                await task
            except:
                pass    # callback will handle exceptions
            await asyncio.sleep(0)    # essential for schedule tasks
        await self.wait('send')
        await self.wait('hook')
