import asyncio as aio
from collections import defaultdict
from functools import partial
import logging
from typing import Mapping

from aioqzone.interface.hook import Emittable
from aioqzone.interface.hook import Event
from aioqzone.type import FeedRep
from aioqzone_feed.type import BaseFeed
from aioqzone_feed.type import FeedContent
from telegram import Message
from telegram.error import BadRequest
from telegram.error import TimedOut

from qzone3tg.utils.iter import aenumerate
from qzone3tg.utils.iter import alist

from . import ChatId
from .atom import MediaMsg
from .limitbot import BotTaskEditter as BTE
from .limitbot import RelaxSemaphore

SendFunc = partial[list[Message]] | partial[Message]
logger = logging.getLogger(__name__)


class StorageEvent(Event):
    """Basic hook event for storage function."""

    async def SaveFeed(self, feed: BaseFeed, msgs_id: list[int]):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param msgs_id: messages id list
        """
        return

    async def get_message_id(self, feed: BaseFeed) -> list[int] | None:
        return

    async def update_message_id(self, feed: BaseFeed, mids: list[int]):
        return

    async def clean(self, seconds: float):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        """
        return

    async def exists(self, feed: FeedRep) -> bool:
        """check if a feed exists in local storage.

        :param feed: feed to check
        :return: whether exists
        """
        return False


class MsgQueue(Emittable[StorageEvent]):
    bid = -1

    def __init__(
        self,
        tasker: BTE,
        forward_map: Mapping[int, ChatId],
        sem: RelaxSemaphore,
        max_retry: int = 2,
    ) -> None:
        self.q: dict[FeedContent, list[SendFunc] | int] = {}
        self.tasker = tasker
        self.fwd2 = forward_map
        self._loop = aio.get_event_loop()
        self.sem = sem
        self.exc = defaultdict(list)
        self.max_retry = max_retry
        self.sending = None

    async def add(self, bid: int, feed: FeedContent):
        if bid != self.bid:
            return
        ids = await self.hook.get_message_id(feed)
        if ids:
            self.q[feed] = ids[-1]
            return  # needn't send again. refer to the message is okay.

        # add a sending task
        tasks = await alist(self.tasker.unify_send(feed))
        for p in tasks:
            p.keywords.update(chat_id=self.fwd2[feed.uin])
        self.q[feed] = tasks

    def new_batch(self, bid: int):
        assert self.sending is None
        assert bid != self.bid
        self.q.clear()
        self.exc.clear()
        self.sem.reset()
        self.bid = bid

    async def send_all(self):
        for k in sorted(self.q):
            self.sending = k
            await self.send_one_feed(k)
        self.sending = None

    async def send_one_feed(self, feed: FeedContent):
        reply: int | None = None
        mids: list[int] = []
        if isinstance(v := self.q[feed], int):
            reply = v
            return
        for f in v:
            f.keywords.update(reply_to_message_id=reply)
            for retry in range(self.max_retry):
                reply = await self.send_one(f, feed)

        # Save the feed after all sending task is done
        self.q[feed] = mids[-1]
        self.add_hook_ref("storage", self.hook.SaveFeed(feed, mids))

    async def send_one(self, f: SendFunc, feed: FeedContent) -> int | None:
        try:
            async with self.sem.context(len(f.keywords.get("media", "0"))):
                # minimize semaphore context
                r = await self._loop.run_in_executor(None, f)
            if isinstance(r, Message):
                return r.message_id
            if isinstance(r, list):
                return r[0].message_id
        except TimedOut as e:
            self.exc[feed].append(e)
            f.keywords["timeout"] = f.keywords.get("timeout", 5) * 2
        except BadRequest as e:
            self.exc[feed].append(e)
            assert isinstance(tasks := self.q[feed], list)
            tasks[tasks.index(f)] = await self.tasker.force_bytes(f)  # type: ignore
        except BaseException as e:
            self.exc[feed].append(e)


class EditableQueue(MsgQueue):
    """Sender with support of editting sending tasks when they are pending."""

    def __init__(
        self,
        tasker: BTE,
        forward_map: Mapping[int, ChatId],
        sem: RelaxSemaphore,
        max_retry: int = 2,
    ) -> None:
        super().__init__(tasker, forward_map, sem, max_retry)

    async def edit_media(self, to: ChatId, mid: int, media: MediaMsg):
        f = partial(
            self.tasker.bot.edit_message_media, to, mid, media=media.wrap_media()
        )
        for _ in range(self.max_retry):
            try:
                async with self.sem.context():
                    return await self._loop.run_in_executor(None, f)
            except TimedOut:
                f.keywords["timeout"] = f.keywords.get("timeout", 5) * 2
            except BadRequest:
                f.keywords["media"] = await self.tasker.force_bytes_inputmedia(
                    f.keywords["media"]
                )

    async def edit(self, bid: int, feed: FeedContent):
        if bid != self.bid:
            # this batch is sent and all info is cleared.
            return await self._edit_sent(feed)
        if not feed in self.q:
            logger.warning("The feed to be update should have been in queue. Skipped.")
            return
        if not self.sending or self.sending < feed:
            return await self._edit_pending(feed)
        if self.sending > feed:
            return await self._edit_sent(feed)
        # The feed is being sent now!!!
        # schedule later!
        self.add_hook_ref("edit", self.edit(bid, feed))

    async def _edit_sent(self, feed: FeedContent):
        await self.wait("storage")
        mids = await self.hook.get_message_id(feed)
        if mids is None:
            logger.warning("Edit media wasn't sent before, skipped.")
            return

        args = await self.tasker.splitter.split(feed)
        for a, mid in zip(args, mids):
            if not isinstance(a, MediaMsg):
                break
            c = self.edit_media(self.fwd2[feed.uin], mid, a.wrap_media())
            self.add_hook_ref("edit", c)

    async def _edit_pending(self, feed: FeedContent):
        tasks = self.q[feed]
        assert isinstance(tasks, list)
        async for i, a in aenumerate(self.tasker.edit_args(feed)):
            # replace the kwarg with new content
            assert tasks[i].func.__name__.endswith(a.meth)
            tasks[i].keywords[a.meth] = a.content
