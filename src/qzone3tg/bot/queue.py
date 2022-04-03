import asyncio as aio
import logging
from abc import abstractmethod
from collections import defaultdict
from functools import partial
from typing import Mapping, cast

from aioqzone.interface.hook import Emittable, Event
from aioqzone_feed.type import BaseFeed, FeedContent
from telegram import Message, ReplyMarkup, TelegramError
from telegram.error import BadRequest, TimedOut

from qzone3tg.utils.iter import aenumerate, alist, countif

from . import ChatId
from .atom import MediaMsg
from .limitbot import BotTaskEditter as BTE
from .limitbot import RelaxSemaphore

SendFunc = partial[list[Message]] | partial[Message]
logger = logging.getLogger(__name__)


class QueueEvent(Event):
    """Basic hook event for storage function."""

    async def SaveFeed(self, feed: BaseFeed, msgs_id: list[int] | None = None):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param msgs_id: messages id list
        """
        return

    async def get_message_id(self, feed: BaseFeed) -> list[int] | None:
        """Get a list of message id from storage.

        :param feed: feed
        :return: the list of message id associated with this feed, or None if not found.
        """
        return

    async def update_message_id(self, feed: BaseFeed, mids: list[int]):
        return


class MsgQueue(Emittable[QueueEvent]):
    bid = -1

    def __init__(
        self,
        tasker: BTE,
        forward_map: Mapping[int, ChatId],
        sem: RelaxSemaphore,
        max_retry: int = 2,
    ) -> None:
        super().__init__()
        self.q: dict[FeedContent, list[SendFunc] | int] = {}
        self.tasker = tasker
        self.fwd2 = forward_map
        self._loop = aio.get_event_loop()
        self.sem = sem
        self.exc = defaultdict(list)
        self.max_retry = max_retry
        self.sending = None
        self.skip_num = 0

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

    @property
    def exc_num(self):
        return countif(self.exc.values(), lambda i: len(i) == self.max_retry)

    def new_batch(self, bid: int):
        assert self.sending is None
        assert bid != self.bid
        self.skip_num = 0
        self.q.clear()
        self.exc.clear()
        self.sem.reset()
        self.bid = bid

    async def send_all(self):
        for k in sorted(self.q):
            self.sending = k
            await self._send_one_feed(k)
        self.sending = None

    async def _send_one_feed(self, feed: FeedContent):
        reply: int | None = None
        mids: list[int] = []
        if isinstance(v := self.q[feed], int):
            reply = v
            return
        for f in v:
            f.keywords.update(reply_to_message_id=reply)
            for retry in range(self.max_retry):
                if (r := await self._send_one(f, feed)) is True:
                    continue
                if isinstance(r, list):
                    mids += r
                    reply = r[-1]
                if retry == 0:
                    self.tasker.bps += self.tasker.eps
                break

        if not mids:
            logger.error(f"feed {feed}, max retry exceeded: {self.exc[feed]}")
            for i, e in enumerate(self.exc[feed], start=1):
                if e:
                    logger.debug("Retry %d", i, exc_info=e)
            # Save the feed even if send failed
            self.add_hook_ref("storage", self.hook.SaveFeed(feed))
            return

        # Save the feed after all sending task is done
        self.q[feed] = mids[-1]
        self.add_hook_ref("storage", self.hook.SaveFeed(feed, mids))

    async def _send_one(self, f: SendFunc, feed: FeedContent) -> list[int] | bool:
        try:
            async with self.sem.context(len(f.keywords.get("media", "0"))):
                # minimize semaphore context
                r = await self._loop.run_in_executor(None, f)
            if isinstance(r, Message):
                return [r.message_id]
            if isinstance(r, list):
                return [i.message_id for i in r]
        except TimedOut as e:
            self.exc[feed].append(e)
            self.tasker.bps /= 2
            self.tasker.inc_timeout(cast(partial, f))
            # TODO: more operations
            return True
        except BadRequest as e:
            self.exc[feed].append(e)
            assert isinstance(tasks := self.q[feed], list)
            tasks[tasks.index(f)] = await self.tasker.force_bytes(f)  # type: ignore
            return True
        except TelegramError as e:
            self.exc[feed].append(e)
            self.exc[feed] += [None] * (self.max_retry - 1)
            logger.error("Uncaught telegram error in send_all.", exc_info=True)
            return False
        except BaseException as e:
            self.exc[feed].append(e)
            self.exc[feed] += [None] * (self.max_retry - 1)
            logger.error("Uncaught error in send_all.", exc_info=True)
            return False
        return False


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
        f = partial(self.tasker.bot.edit_message_media, to, mid, media=media.wrap_media())
        for _ in range(self.max_retry):
            try:
                async with self.sem.context():
                    return await self._loop.run_in_executor(None, f)
            except TimedOut:
                f.keywords["timeout"] = f.keywords.get("timeout", 5) * 2
            except BadRequest:
                f.keywords["media"] = await self.tasker.force_bytes_inputmedia(f.keywords["media"])
            except TelegramError:
                logger.error("Uncaught telegram error when editting media.", exc_info=True)
            except BaseException:
                logger.error("Uncaught error when editting media.", exc_info=True)
                return

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
