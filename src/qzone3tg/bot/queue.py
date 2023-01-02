import asyncio
import logging
from collections import defaultdict
from typing import Mapping, Sequence

from aioqzone_feed.type import BaseFeed, FeedContent
from httpx import TimeoutException
from qqqr.event import Emittable, Event
from telegram import Message
from telegram.error import BadRequest, TelegramError, TimedOut

from qzone3tg.utils.iter import alist, countif

from . import BotProtocol, ChatId, GroupMedia
from .atom import LIM_TXT, MediaGroupPartial, MediaPartial, MsgPartial, stringify_entities
from .limitbot import BotTaskEditter as BTE

SendFunc = MediaGroupPartial | MsgPartial
log = logging.getLogger(__name__)


class QueueEvent(Event):
    """Basic hook event for storage function."""

    async def SaveFeed(self, feed: BaseFeed, mids: list[int] | None = None):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param msgs_id: messages id list
        """
        return

    async def GetMid(self, feed: BaseFeed) -> Sequence[int]:
        """Get a list of message id from storage.

        :param feed: feed
        :return: the list of message id associated with this feed, or None if not found.
        """
        return ()


class MsgQueue(Emittable[QueueEvent]):
    bid = -1

    def __init__(
        self,
        bot: BotProtocol,
        tasker: BTE,
        forward_map: Mapping[int, ChatId],
        max_retry: int = 2,
    ) -> None:
        super().__init__()
        self.q: dict[FeedContent, list[SendFunc] | int] = {}
        self.bot = bot
        self.tasker = tasker
        self.fwd2 = forward_map
        self._loop = asyncio.get_event_loop()
        self.exc = defaultdict(list)
        self.max_retry = max_retry
        self.sending = None
        self.skip_num = 0

    async def add(self, bid: int, feed: FeedContent):
        if bid != self.bid:
            log.warning(f"incoming bid ({bid}) != current bid ({self.bid}), dropped.")
            return
        await self.wait("storage")  # wait for all pending storage tasks
        ids = await self.hook.GetMid(feed)
        if ids:
            log.info(f"Feed {feed} is sent, use existing message id: {ids[-1]}")
            self.q[feed] = ids[-1]
            return  # needn't send again. refer to the message is okay.

        # add a sending task
        tasks = await alist(self.tasker.unify_send(feed))
        for p in tasks:
            p.kwds.update(to=self.fwd2[feed.uin])

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
        self.bid = bid

    async def send_all(self):
        try:
            return await self._send_all_unsafe()
        finally:
            self.sending = None

    async def _send_all_unsafe(self):
        uin2lastfeed: dict[int, FeedContent] = {}
        for k in sorted(self.q):
            if (
                (last_feed := uin2lastfeed.get(k.uin))
                and isinstance(last_mid := self.q[last_feed], int)
                and k.abstime - last_feed.abstime < 1000
            ):
                # compare with last feed
                if last_feed.entities == k.entities:
                    log.info(f"Feed {last_feed} and {k} has the same content. Skip the last one.")
                    # if all entities are the same, save the last mid and continue.
                    self.q[k] = last_mid
                    self.add_hook_ref("storage", self.hook.SaveFeed(k, [last_mid]))
                    uin2lastfeed[k.uin] = k
                    continue

            self.sending = k
            await self._send_one_feed(k)
            uin2lastfeed[k.uin] = k

    async def _send_one_feed(self, feed: FeedContent):
        reply: int | None = None
        mids: list[int] = []
        if (v := self.q.get(feed)) is None:
            # BUG: why is KeyError?
            log.fatal(f"feed MISS!!! feed={feed}, q={self.q}")
            return
        elif isinstance(v, int):
            log.debug(f"feed {feed} is sent before.")
            return

        for f in v:
            f.kwds.update(reply_to_message_id=reply)
            for retry in range(self.max_retry):
                if (r := await self._send_one_atom(f, feed)) is True:
                    log.debug("Send atom suggest to resend, resend at once.")
                    continue
                if isinstance(r, list):
                    mids += r
                    reply = r[-1]
                if retry == 0:
                    self.tasker.bps += self.tasker.eps
                    log.debug(f"increased bps to {self.tasker.bps:.2f}")
                break

        if mids:
            log.info(f"发送成功：{feed.uin}({feed.nickname}){feed.abstime}")
        else:
            log.error(f"feed {feed}, max retry exceeded: {self.exc[feed]}")
            for i, e in enumerate(self.exc[feed], start=1):
                if e:
                    log.debug("Retry %d", i, exc_info=e)
            # Save the feed even if send failed
            self.add_hook_ref("storage", self.hook.SaveFeed(feed))
            return

        # Save the feed after all sending task is done
        self.q[feed] = mids[-1]
        self.add_hook_ref("storage", self.hook.SaveFeed(feed, mids))

    async def _send_one_atom(self, f: SendFunc, feed: FeedContent) -> list[int] | bool:
        """
        :param f: a :class:`MsgPartial` object
        :param feed: the feed to be sent
        :return: a list of message id if success, otherwise whether to resend
        """
        try:
            r = await f(self.bot)
            match r:
                case Message():
                    return [r.message_id]
                case list():
                    return [i.message_id for i in r]
                case _:
                    log.fatal(f"Unexpected send return type: {type(r)}")
        except TimedOut as e:
            log.debug(f"current timeout={f.timeout:.2f}")
            self.exc[feed].append(e)
            self.tasker.bps /= 2
            self.tasker.inc_timeout(f)
            log.info("发送超时：等待重发")
            log.debug(f"increased timeout={f.timeout:.2f}")
            if isinstance(e.__cause__, TimeoutException):
                log.debug("the timeout request is:", e.__cause__.request)
            if f.text and len(f.text) < LIM_TXT:
                f.text = "🔁" + f.text
            return True
        except BadRequest as e:
            self.exc[feed].append(e)
            assert isinstance(tasks := self.q[feed], list)
            if isinstance(f, (MediaPartial, MediaGroupPartial)):
                tasks[tasks.index(f)] = await self.tasker.force_bytes(f)
                return True
            log.error("Got BadRequest from send_%s!", f.meth, exc_info=e)
        except TelegramError as e:
            self.exc[feed].append(e)
            self.exc[feed] += [None] * (self.max_retry - 1)
            log.error("Uncaught telegram error in send_%s.", f.meth, exc_info=e)
        except BaseException as e:
            self.exc[feed].append(e)
            self.exc[feed] += [None] * (self.max_retry - 1)
            log.error("Uncaught error in send_%s.", f.meth, exc_info=e)
        return False


class EditableQueue(MsgQueue):
    """Sender with support of editting sending tasks when they are pending."""

    def __init__(
        self,
        bot: BotProtocol,
        tasker: BTE,
        forward_map: Mapping[int, ChatId],
        max_retry: int = 2,
    ) -> None:
        super().__init__(bot, tasker, forward_map, max_retry)

    async def edit_media(self, to: ChatId, mid: int, media: GroupMedia):
        kw = {}
        for _ in range(self.max_retry):
            try:
                return await self.bot.edit_message_media(to, mid, media, **kw)
            except TimedOut:
                kw["timeout"] = kw.get("timeout", 5) * 2  # TODO
            except BadRequest:
                media = await self.tasker.force_bytes_inputmedia(media)
            except TelegramError:
                log.error("Uncaught telegram error when editting media.", exc_info=True)
            except BaseException:
                log.error("Uncaught error when editting media.", exc_info=True)
                return

    async def edit(self, bid: int, feed: FeedContent):
        if bid != self.bid:
            # this batch is sent and all info is cleared.
            return await self._edit_sent(feed)
        if not feed in self.q:
            log.warning("The feed to be update should have been in queue. Skipped.")
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
        mids = await self.hook.GetMid(feed)
        mids = list(mids)
        if not mids:
            log.error("Edit media wasn't sent before, skipped.")
            return

        args = await alist(self.tasker.unify_send(feed))
        for a in args:
            if isinstance(a, MediaPartial):
                mid = mids.pop(0)
                c = self.edit_media(self.fwd2[feed.uin], mid, a.wrap_media())
                self.add_hook_ref("edit", c)
            elif isinstance(a, MediaGroupPartial):
                for i in a.medias:
                    mid = mids.pop(0)
                    self.add_hook_ref("edit", self.edit_media(self.fwd2[feed.uin], mid, i))
                    pass
            else:
                break

    async def _edit_pending(self, feed: FeedContent):
        # replace the kwarg with new content
        tasks = await alist(self.tasker.unify_send(feed))
        for p in tasks:
            p.kwds.update(to=self.fwd2[feed.uin])

        self.q[feed] = tasks
