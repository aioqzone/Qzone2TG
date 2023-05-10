from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Mapping, Sequence, TypeGuard

from aioqzone.type.internal import PersudoCurkey
from aioqzone_feed.type import BaseFeed, FeedContent
from httpx import TimeoutException
from qqqr.event import Emittable, Event
from telegram import Bot, Message
from telegram.constants import MessageLimit
from telegram.error import BadRequest, TelegramError, TimedOut

from qzone3tg.type import FeedPair
from qzone3tg.utils.iter import countif

from .atom import MediaGroupPartial, MediaPartial, MsgPartial
from .splitter import FetchSplitter, Splitter

if TYPE_CHECKING:
    from . import ChatId, ReplyMarkup, SupportMedia

    Atom = MediaGroupPartial | MsgPartial
    MidOrAtoms = list[Atom] | list[int]

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

    async def reply_markup(
        self, feed: FeedContent, need_forward: bool
    ) -> FeedPair[ReplyMarkup | None]:
        """Allow app to generate `reply_markup` according to its own policy.

        :param feed: the feed to generate reply_markup
        :param need_forward: whether the forward reply_markup will be used.
            If this is False, you can simply set `forward` field to None.
        :return: A :class:`FeedPair` object contains `ReplyMarkup`s."""
        return FeedPair(None, None)


def is_mids(l: MidOrAtoms) -> TypeGuard[list[int]]:
    assert l
    if all(isinstance(i, int) for i in l):
        return True
    return False


def is_atoms(l: MidOrAtoms) -> TypeGuard[list[Atom]]:
    assert l
    if all(isinstance(i, MsgPartial) for i in l):
        return True
    return False


class MsgQueue(Emittable[QueueEvent]):
    bid = -1
    q: dict[FeedContent, FeedPair[MidOrAtoms]]

    def __init__(
        self,
        bot: Bot,
        splitter: Splitter,
        forward_map: Mapping[int, ChatId],
        max_retry: int = 2,
    ) -> None:
        super().__init__()
        self.q = defaultdict(lambda: FeedPair([], []))
        self.bot = bot
        self.splitter = splitter
        self.forward_map = forward_map
        self.exc_groups = defaultdict(list)
        self.max_retry = max_retry
        self.sending = None
        self.skip_num = 0

    def add(self, bid: int, feed: FeedContent):
        """Add a feed into queue. The :obj:`bid` should equal to current :obj:`~MsgQueue.bid`, or
        the feed will be dropped directly.

        This operation will:

        1. Query message ids of the forward feed, if `feed` has one. If that feed is sent before, we can skip
            sending and just reply to its id when sending the feed itself.
        2. Split the feed into atoms.
        3. Add ``chat_id`` field into atom keywords, according to :obj:`.forward_map`.
        4. Attach `reply_markup` to atoms.

        :param bid: batch id, should equals to current `.bid`.
        :param feed: the feed to add into queue.
        """
        if bid != self.bid:
            log.warning(f"incoming bid ({bid}) != current bid ({self.bid}), dropped.")
            return
        assert not self._tasks["db_write"], 'call wait("db_write") after a batch ends!'

        async def query_forward_mids() -> FeedPair[bool]:
            pair = FeedPair(True, True)
            if ids := await self.hook.GetMid(feed):
                log.info(f"Forward feed {feed} is sent before, using existing message ids: {ids}")
                self.q[feed].feed = list(ids)
                pair.feed = False
                return pair

            if isinstance(feed.forward, BaseFeed):
                if ids := await self.hook.GetMid(feed.forward):
                    log.info(
                        f"Forward feed {feed} is sent before, using existing message ids: {ids}"
                    )
                    self.q[feed].forward = list(ids)
                    pair.forward = False

            return pair

        async def split_feed(need_forward: bool):
            return await self.splitter.split(feed, need_forward=need_forward)

        def set_atom_keywords(
            atoms: FeedPair[Sequence[MsgPartial]],
            reply_markups: FeedPair[ReplyMarkup | None],
            need_forward: bool,
        ):
            # log input
            log.debug(f"need_forward = {need_forward}")
            log.debug(f"got atoms: {atoms}")
            log.debug(f"got reply_markups: {reply_markups}")

            # set chat_id fields
            chat_id = self.forward_map[feed.uin]
            for p in atoms.feed:
                p.kwds.update(chat_id=chat_id)
            if need_forward:
                for p in atoms.forward:
                    p.kwds.update(chat_id=chat_id)

            # set reply_markup fields
            if reply_markups.feed:
                if part := next(
                    filter(lambda p: not isinstance(p, MediaGroupPartial), atoms.feed), None
                ):
                    part.reply_markup = reply_markups.feed
            if need_forward and reply_markups.forward:
                if part := next(
                    filter(lambda p: not isinstance(p, MediaGroupPartial), atoms.forward), None
                ):
                    part.reply_markup = reply_markups.forward

            # push into queue
            self.q[feed].feed = list(atoms.feed)
            if need_forward:
                self.q[feed].forward = list(atoms.forward)

        tid = PersudoCurkey(feed.uin, feed.abstime)
        self.q[feed]  # create item
        task_get_mids = self.add_hook_ref(tid, query_forward_mids())
        task_get_mids.add_done_callback(
            lambda p: (has_mids := p.result()).feed
            and self.add_hook_ref(
                tid,
                asyncio.gather(
                    split_feed(need_forward=has_mids.forward),
                    self.hook.reply_markup(feed, need_forward=has_mids.forward),
                ),
            ).add_done_callback(lambda s: set_atom_keywords(*s.result(), has_mids.forward))
        )

    @property
    def exc_num(self):
        return countif(self.exc_groups.values(), lambda i: len(i) == self.max_retry)

    def new_batch(self, bid: int):
        assert self.sending is None
        assert bid != self.bid
        self.skip_num = 0
        self.q.clear()
        self.exc_groups.clear()
        self.bid = bid

    async def send_all(self):
        try:
            await self._send_all_unsafe()
        finally:
            self.sending = None

    async def _send_all_unsafe(self):
        uin2lastfeed: dict[int, FeedContent] = {}
        for k in sorted(self.q):
            if (
                (last_feed := uin2lastfeed.get(k.uin))
                and self.q[last_feed].feed
                and is_mids(last_mids := self.q[last_feed].feed)
                and k.abstime - last_feed.abstime < 1000
            ):
                # compare with last feed
                if last_feed.entities == k.entities:
                    log.info(f"Feed {last_feed} and {k} has the same content. Skip the last one.")
                    # if all entities are the same, save the last mid and continue.
                    self.q[k].feed = last_mids
                    self.add_hook_ref("db_write", self.hook.SaveFeed(k, last_mids))
                    uin2lastfeed[k.uin] = k
                    continue

            self.sending = k
            await self._send_one_feed(k)
            uin2lastfeed[k.uin] = k

        # clear storage taskset
        await self.wait("db_write")

    async def _send_one_feed(self, feed: FeedContent):
        assert feed in self.q
        log.debug(f"sending feed {feed.uin}{feed.abstime}.")

        tid = PersudoCurkey(feed.uin, feed.abstime)
        await self.wait(tid)

        atoms = self.q[feed]
        reply: int | None = None

        async def _send_atom_with_reply(atom: Atom, feed: FeedContent):
            nonlocal reply
            if reply is not None:
                atom.kwds.update(reply_to_message_id=reply)
            if r := await self._send_atom(atom, feed):
                reply = r[-1]
            return r

        # send forward
        if atoms.forward:
            if is_atoms(atoms.forward):
                assert isinstance(feed.forward, FeedContent)
                mids = sum(
                    [await _send_atom_with_reply(p, feed.forward) for p in atoms.forward], []
                )
                self.add_hook_ref("db_write", self.hook.SaveFeed(feed.forward, mids))
                atoms.forward = mids
            else:
                assert is_mids(atoms.forward)
                log.info(f"Forward feed is skipped with message ids {atoms.forward}")
                if atoms.forward:
                    reply = atoms.forward[-1]

        # send feed
        assert atoms.feed
        if is_atoms(atoms.feed):
            mids = sum([await _send_atom_with_reply(p, feed) for p in atoms.feed], [])
            self.add_hook_ref("db_write", self.hook.SaveFeed(feed, mids))
            atoms.feed = mids
        else:
            assert is_mids(atoms.feed)
            log.info(f"Feed is skipped with message ids {atoms.feed}")
            if atoms.feed:
                reply = atoms.feed[-1]

    async def _send_atom(self, atom: Atom, feed: FeedContent) -> list[int]:
        for _ in range(self.max_retry):
            match await self._send_atom_once(atom, feed):
                case MsgPartial() as atom:
                    continue
                case None:
                    break
                case list() as r:
                    return r
        return []

    async def _send_atom_once(self, atom: Atom, feed: FeedContent) -> list[int] | Atom | None:
        """
        :param f: a :class:`MsgPartial` object
        :param feed: the feed to be sent
        :return: a list of message ids if success, or a `MsgPartial` if resend, or None if skip.
        """
        log.debug(f"sending atom {atom}.")
        try:
            match await atom(self.bot):
                case Message() as r:
                    log.debug("atom is sent successfully.")
                    return [r.message_id]
                case r if isinstance(r, Sequence):
                    log.debug("atom is sent successfully.")
                    return [i.message_id for i in r]
        except TimedOut as e:
            self.exc_groups[feed].append(e)
            log.debug(f"current timeout={atom.timeout:.2f}")
            log.info("发送超时：等待重发")
            # log.debug(f"increased timeout={atom.timeout:.2f}")
            if isinstance(e.__cause__, TimeoutException):
                log.debug("the timeout request is:", e.__cause__.request)
            if atom.text is None or len(atom.text) < (
                MessageLimit.MAX_TEXT_LENGTH
                if atom.meth == "message"
                else MessageLimit.CAPTION_LENGTH
            ):
                atom.text = "🔁" + (atom.text or "")
            return atom
        except BadRequest as e:
            self.exc_groups[feed].append(e)
            reason = e.message.lower()
            log.error(f"BadRequest in _send_atom_once: {reason}")
            if "replied message not found" in reason:
                if "reply_to_message_id" in atom.kwds:
                    atom.kwds.pop("reply_to_message_id")
                    log.warning("'reply_to_message_id' keyword removed.")
                    return atom
                log.error("'reply_to_message_id' keyword not found, skip.")
                log.debug(atom)
                return None
            elif "wrong file" in reason:
                if isinstance(self.splitter, FetchSplitter):
                    if isinstance(atom, (MediaPartial, MediaGroupPartial)):
                        return await self.splitter.force_bytes(atom)
                    log.error("no file is to be sent, skip.")
                    log.debug(atom)
                    return None
                log.warning("fetch is not enabled, skip.")
        except TelegramError as e:
            self.exc_groups[feed].append(e)
            log.error("Uncaught telegram error in send_%s.", atom.meth, exc_info=e)
        except BaseException as e:
            self.exc_groups[feed].append(e)
            log.error("Uncaught error in send_%s.", atom.meth, exc_info=e)
        return None
