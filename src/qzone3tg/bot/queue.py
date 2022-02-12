"""A message queue for sending feeds."""

from abc import abstractmethod
import asyncio
from collections import defaultdict
import logging
import time
from typing import Callable, Optional, Union

from aioqzone.interface.hook import Emittable
from aioqzone.interface.hook import Event
from aioqzone.type import FeedRep
from aioqzone_feed.type import BaseFeed
from aioqzone_feed.type import FeedContent

logger = logging.getLogger(__name__)


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


class StorageEvent(Event):
    """Basic hook event for storage function."""
    async def SaveFeed(self, feed: BaseFeed, msgs_id: list[int]):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param msgs_id: messages id list
        """
        return

    async def get_message_id(self, feed: BaseFeed) -> Optional[list[int]]:
        return

    async def update_message_id(self, feed: BaseFeed, mids: list[int]):
        return

    async def clean(self, seconds: float):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        """
        return

    async def exists(self, feed: FeedRep) -> bool:
        """check if a feed exists in this database.

        :param feed: feed to check
        :return: whether exists
        """
        return False


class ForwardEvent(Event, Emittable[StorageEvent]):
    @abstractmethod
    async def SendNow(
        self,
        feed: FeedContent,
        dep: asyncio.Task[list[int]] = None,
        last_exc: BaseException = None,
    ) -> list[int]:
        """This feed is scheduled and must be send at once. Subclass need not send
        `feed.forward` if it is a :external:class:`aioqzone_feed.type.FeedContent` as well.
        If it does, it will be scheduled before this feed, and the task will be passed through `dep`.
        Subclass can await for `dep` to ensure the task is done.

        If some error occurs, `last_exc` will be passed, which is the exception in last run.

        :param feed: The feed to be send.
        :param dep: Task that should be await before current sending, defaults to None
        :param last_exc: Exception occurs in last schedule, defaults to None
        :return: message id
        """
        if dep: await dep

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
            if (exc := t.exception()) is None:
                logger.info('Task success. Removed.')
                return    # task has been removed by add_hook_ref
            self.excs[feed].append(exc)
            if len(self.excs[feed]) < self._retry:
                logger.warning(f'Task failed # {len(self.excs[feed])}, retry.')
                task = self.add_hook_ref('send', self.hook.SendNow(feed, last_exc=exc))
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
        self._point = 2 * val - 1    # which feed should be sent in advance

    def pending_feeds(self, reverse: bool = True):
        if not reverse: return filter(None, self.buffer.values())
        it = sorted(self.buffer.items(), key=lambda t: t[0], reverse=True)
        return filter(None, (i[1] for i in it))

    def pending_tasks(self):
        return self._tasks['send']

    async def add(self, bid: int, feed: FeedContent):
        if isinstance(feed.forward, FeedContent) and \
            await self.hook.hook.get_message_id(feed.forward) is None:
            # schedule forwardee before forwarder
            self.buffer[2 * bid + 1] = feed.forward
        self.buffer[bid << 1] = feed
        if self._max == 0: return    # skip if upper bound unknown

        task = next(iter(self._tasks['send']), None)

        while self._point >= 0:
            assert self._point & 1, 'pointer should point at an odd num'
            for i in range(2):
                if (f := self.buffer.get(self._point - i)):    # if this bid should be sent
                    logger.debug('bid=%d is ready.', self._point)
                else:
                    if i == 0: continue
                    return

                self.buffer[self._point - i] = None    # remove the feed from buffer
                task = self.add_hook_ref(
                    'send', self.hook.SendNow(f, task)
                )    # pass the first task when i=1
                task = self._add_handler(task, f)
                logger.info(f'Feed scheduled in add: bid={bid}, task={task}')
                if i == 1: self._point -= 2    # donot care whether succ or not

    async def send_all(self):
        assert len(self.buffer), "Wait until all item arrive"
        await self.wait('send')
        for feed in self.pending_feeds(reverse=True):
            task = self.add_hook_ref('send', self.hook.SendNow(feed))
            self._add_handler(task, feed)
            try:
                await self.wait('send')
            except:
                pass    # callback will handle exceptions
            await asyncio.sleep(0)    # essential for schedule tasks
        await self.wait('hook')
