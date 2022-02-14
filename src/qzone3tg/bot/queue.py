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
BUBBLE = object.__new__(FeedContent)


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

    async def MaxRetryExceed(self, feed: FeedContent, *exc):
        pass


class MsgBarrier(Emittable[ForwardEvent]):
    buffer: set[FeedContent]
    excs: dict[FeedContent, list[BaseException]]
    waiting: bool
    """Set this to save all feeds in this barrier. Set to false will emit sending at once."""

    __slots__ = ('buffer', 'excs', 'waiting', '_retry')

    def __init__(self, max_retry: int = 2) -> None:
        super().__init__()
        self.buffer = set()
        self.excs = defaultdict(list)
        self._retry = max_retry
        self.waiting = False

    def send_all(self):
        while self.buffer:
            feed = self.buffer.pop()
            task = self.add_hook_ref('send', self.hook.SendNow(feed))
            self._add_handler(task, feed)

    def add(self, feed: FeedContent):
        if feed is BUBBLE: return
        if self.waiting:
            self.buffer.add(feed)
        else:
            task = self.add_hook_ref('send', self.hook.SendNow(feed))
            self._add_handler(task, feed)
            logger.info(f'Feed scheduled in add: task={task}')

    def _add_handler(self, task: asyncio.Task, feed: FeedContent):
        def check_succ(t: asyncio.Task):
            if (exc := t.exception()) is None:
                logger.info('Task success. Removed.')
                return    # task has been removed by add_hook_ref
            self.excs[feed].append(exc)
            if len(self.excs[feed]) < self._retry:
                logger.warning('Task failed #%d, retry.', len(self.excs[feed]))
                task = self.add_hook_ref('send', self.hook.SendNow(feed, last_exc=exc))
                self._add_handler(task, feed)
                return
            self.add_hook_ref('hook', self.hook.MaxRetryExceed(feed, *self.excs[feed]))

        task.add_done_callback(check_succ)
        return task


class MsgScheduler(Emittable[ForwardEvent]):
    """Buf a batch of message and schedule them with hook."""
    buffer: dict[int, Optional[FeedContent]]
    __slots__ = ('_max', '_waiting', 'retry', 'buffer', 'excs')

    def __init__(self, val: int = 0, max_retry: int = 2) -> None:
        assert max_retry >= 0
        super().__init__()
        self.buffer = {}
        self.excs = defaultdict(list)
        self._max = 0
        self.retry = max_retry
        if val > 0: self.set_upper_bound(val)

    def set_upper_bound(self, val: int):
        assert val > 0
        self._max = val
        self._waiting = val - 1

    def pending_feeds(self, reverse: bool = True):
        if not reverse: return filter(None, self.buffer.values())
        it = sorted(self.buffer.items(), key=lambda t: t[0], reverse=True)
        return filter(None, (i[1] for i in it))

    def pending_tasks(self):
        return self._tasks['send']

    async def add(self, bid: int, feed: FeedContent):
        """Add a feed to scheduler. It will buffered on `2 * bid`, and its forwardee, if any,
        will be buffered at `2 * bid + 1`. If the bid is the expected one, it will be submit
        as a task at once.

        If any send task is done but its callback is not called, it will be called to clear
        the task set."""

        if not feed is BUBBLE and isinstance(feed.forward, FeedContent) and \
            await self.hook.hook.get_message_id(feed.forward) is None:
            # schedule forwardee before forwarder
            self.buffer[2 * bid + 1] = feed.forward
        self.buffer[bid << 1] = feed

        if self._max == 0: return    # skip if upper bound unknown
        if self.pending_tasks() and all(i.done() for i in self._tasks['send']):
            logger.debug('Some task is done but callback not called. Await.')
            await self.wait('send')

        if (f := self.buffer.get(self._waiting * 2)) is None:
            logger.debug(f'bid {bid} added but expected {self._waiting}, skip.')
            return
        await self._schedule_expected()

    async def _schedule_expected(self):
        """Schedule the feed buffered on `waiting` pointer."""

        if (f := self.buffer.get(self._waiting * 2)) is None:
            return

        if self.pending_tasks():
            logger.debug('Task scheduled but preceding task hasnot done. Send at once!')
            await self.wait('send')

        logger.debug(f'bid={self._waiting} is ready to send')
        dep = None
        if (df := self.buffer.get(self._waiting * 2 + 1)):
            self.buffer[self._waiting * 2 + 1] = None
            dep = self.add_hook_ref('send', self.hook.SendNow(df))
            self._add_handler(dep, df)

        self.buffer[self._waiting * 2] = None
        if f is BUBBLE:
            logger.info(f"Bubble detected. Skipped!")
            self._waiting -= 1
            return
        else:
            task = self.add_hook_ref('send', self.hook.SendNow(f, dep=dep))
            self._add_handler(task, f)
            logger.info(f'Feed scheduled in advance: bid={self._waiting}, task={task}, dep={dep}')

    def _add_handler(self, task: asyncio.Task, feed: FeedContent):
        def check_succ(t: asyncio.Task):
            if (exc := t.exception()) is None:
                logger.info('Task success. Removed.')
                self._waiting -= 1
                return    # task has been removed by add_hook_ref
            self.excs[feed].append(exc)
            if len(self.excs[feed]) < self.retry:
                logger.warning('Task failed #%d, retry.', len(self.excs[feed]))
                task = self.add_hook_ref('send', self.hook.SendNow(feed, last_exc=exc))
                self._add_handler(task, feed)
                return
            self.add_hook_ref('hook', self.hook.MaxRetryExceed(feed, *self.excs[feed]))
            self._waiting -= 1

        task.add_done_callback(check_succ)
        return task

    async def send_all(self):
        assert len(self.buffer), "Wait until all item arrive"
        # clear all bubble since we needn't it now
        for k, v in self.buffer.items():
            if v is BUBBLE: self.buffer[k] = None
        # await existing send task
        await self.wait('send')
        # await in order
        for feed in self.pending_feeds(reverse=True):
            task = self.add_hook_ref('send', self.hook.SendNow(feed))
            self._add_handler(task, feed)
            try:
                await self.wait('send')
            except:
                pass    # callback will handle exceptions
            await asyncio.sleep(0)    # essential for schedule tasks
        # await for hooks
        await self.wait('hook')
