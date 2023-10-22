import asyncio
import logging
from bisect import insort
from collections import defaultdict
from typing import Mapping, Sequence, TypeGuard

from aiogram import Bot
from aiogram.exceptions import AiogramError
from aiogram.exceptions import TelegramBadRequest as BadRequest
from aiogram.types.message import Message
from aioqzone_feed.type import FeedContent
from tylisten.futstore import FutureStore

from qzone3tg.utils.iter import countif

from . import *
from .atom import MediaGroupPartial, MediaPartial, MsgPartial
from .splitter import FetchSplitter, Splitter

Atom = MediaGroupPartial | MsgPartial
MidOrAtoms = list[Atom] | list[int]
MidOrFeed = FeedContent | list[int]

log = logging.getLogger(__name__)


def all_is_mid(l: MidOrAtoms) -> TypeGuard[list[int]]:
    assert l
    if all(isinstance(i, int) for i in l):
        return True
    return False


def all_is_atom(l: MidOrAtoms) -> TypeGuard[list[Atom]]:
    assert l
    if all(isinstance(i, MsgPartial) for i in l):
        return True
    return False


class QueueHook:
    async def reply_markup(self, feed: FeedContent) -> ReplyMarkup | None:
        """Allow app to generate `reply_markup` according to its own policy.

        :param feed: the feed to generate reply_markup
        :return: `ReplyMarkup` or None."""


class SendQueue(QueueHook):
    bid = -1
    feed_state: dict[FeedContent, MidOrAtoms]
    """Feed to sent/unsent atoms."""
    ch_feed: dict[FeedContent, FutureStore]
    """Future store per feed."""
    _send_order: list[FeedContent]
    _dup_cache: dict[int, FeedContent]
    """A cache that saves feed according to uin. It is used to check if two feeds are duplicated."""

    def __init__(
        self,
        bot: Bot,
        splitter: Splitter,
        forward_map: Mapping[int, ChatId],
        max_retry: int = 2,
    ) -> None:
        super().__init__()
        self.feed_state = defaultdict(list)
        self.ch_feed = defaultdict(lambda: FutureStore())
        self._send_order = []
        self._dup_cache = {}

        self.bot = bot
        self.splitter = splitter
        self.forward_map = forward_map
        self.exc_groups = defaultdict(list)
        self.max_retry = max_retry
        self.drop_num = 0
        """number of dropped feeds in this batch"""

    @property
    def exc_num(self):
        return countif(self.exc_groups.values(), lambda i: len(i) == self.max_retry)

    def new_batch(self, bid: int):
        assert bid != self.bid
        self.drop_num = 0
        self.feed_state.clear()
        self.ch_feed.clear()
        self._send_order.clear()
        self._dup_cache.clear()
        self.exc_groups.clear()
        self.bid = bid

    def drop(self, bid: int, feed: FeedContent):
        if bid != self.bid:
            log.warning(f"incoming bid ({bid}) != current bid ({self.bid}), skipped.")
            return
        self.drop_num += 1

    def add(self, bid: int, feed: FeedContent, forward_mid: list[int] | None = None):
        """Add a feed into queue. The :obj:`bid` should equal to current :obj:`~MsgQueue.bid`, or
        the feed will be dropped directly.

        This operation will:

        1. Split the feed into atoms.
        2. Add ``chat_id`` field into atom keywords, according to :obj:`.forward_map`.
        3. Attach `reply_markup` to atoms.

        :param bid: batch id, should equals to current `.bid`.
        :param feed: the feed to add into queue.
        :param forward_mid: forward message ids.
        """
        if bid != self.bid:
            log.warning(f"incoming bid ({bid}) != current bid ({self.bid}), skipped.")
            return

        last_feed = self._dup_cache.get(feed.uin)
        self._dup_cache[feed.uin] = feed

        # check if this is duplicated
        if (
            last_feed
            and self.feed_state[last_feed]
            and abs(feed.abstime - last_feed.abstime) < 1000
        ):
            # compare with last feed
            if last_feed.entities == feed.entities:
                log.info(f"Feed {last_feed} and {feed} has the same content. Skip the last one.")
                # if all entities are the same, save the last mid and continue.
                return

        def set_atom_keywords(
            atoms: Sequence[MsgPartial],
            reply_markup: ReplyMarkup | None,
        ):
            # log input
            log.debug(f"got atoms: {atoms}")
            log.debug(f"got reply_markup: {reply_markup}")

            # set chat_id fields
            chat_id = self.forward_map[feed.uin]
            for p in atoms:
                p.kwds.update(chat_id=chat_id)

            # set reply_markup fields
            if reply_markup:
                if part := next(
                    filter(lambda p: not isinstance(p, MediaGroupPartial), atoms), None
                ):
                    part.reply_markup = reply_markup

            # push into queue
            self.feed_state[feed] = list(atoms)

        insort(self._send_order, feed)
        self._send_order[feed.abstime] = feed
        self.ch_feed[feed].add_awaitable(
            asyncio.gather(
                self.splitter.split(feed),
                self.reply_markup(feed),
            ),
        ).add_done_callback(lambda s: set_atom_keywords(*s.result()))

        if forward_mid:
            assert isinstance(feed.forward, FeedContent)
            self.feed_state[feed.forward] = forward_mid
        elif isinstance(feed.forward, FeedContent):
            self.ch_feed[feed.forward].add_awaitable(
                asyncio.gather(
                    self.splitter.split(feed.forward),
                    self.reply_markup(feed.forward),
                ),
            ).add_done_callback(lambda s: set_atom_keywords(*s.result()))

    def send_all(self) -> dict[FeedContent, asyncio.Future[None]]:
        task_dict: dict[FeedContent, asyncio.Future[None]] = {}
        uin2lastfeed: dict[int, FeedContent] = {}

        for feed in self._send_order:
            if (
                (last_feed := uin2lastfeed.get(feed.uin))
                and self.feed_state[last_feed]
                and all_is_mid(last_mids := self.feed_state[last_feed])
                and feed.abstime - last_feed.abstime < 1000
            ):
                # compare with last feed
                if last_feed.entities == feed.entities:
                    log.info(
                        f"Feed {last_feed} and {feed} has the same content. Skip the last one."
                    )
                    # if all entities are the same, save the last mid and continue.
                    self.feed_state[feed] = last_mids
                    uin2lastfeed[feed.uin] = feed
                    continue

            task_dict[feed] = self.ch_feed[feed].add_awaitable(self._send_one_feed(feed))
            uin2lastfeed[feed.uin] = feed

        return task_dict

    async def _send_one_feed(self, feed: FeedContent) -> None:
        assert feed in self.feed_state
        log.debug(f"sending feed {feed.uin}{feed.abstime}.")

        await self.ch_feed[feed].wait(wait_new=False)

        atoms = self.feed_state[feed]
        reply: int | None = None

        async def _send_atom_with_reply(atom: Atom, feed: FeedContent):
            nonlocal reply
            if reply is not None:
                atom.kwds.update(reply_to_message_id=reply)
            if r := await self._send_atom(atom, feed):
                reply = r[-1]
            return r

        # send forward
        if isinstance(feed.forward, FeedContent) and (
            atoms_forward := self.feed_state[feed.forward]
        ):
            if all_is_atom(atoms_forward):
                mids = sum(
                    [await _send_atom_with_reply(p, feed.forward) for p in atoms_forward], []
                )
                self.feed_state[feed.forward] = mids
            else:
                assert all_is_mid(atoms_forward)
                log.info(f"Forward feed is skipped with message ids {atoms_forward}")
                if atoms_forward:
                    reply = atoms_forward[-1]

        # send feed
        assert atoms
        if all_is_atom(atoms):
            mids = sum([await _send_atom_with_reply(p, feed) for p in atoms], [])
            self.feed_state[feed] = mids
        else:
            assert all_is_mid(atoms)
            log.info(f"Feed is skipped with message ids {atoms}")
            if atoms:
                reply = atoms[-1]

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
        :param atom: a :class:`MsgPartial` object
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
        except asyncio.TimeoutError as e:
            self.exc_groups[feed].append(e)
            log.debug(f"current timeout={atom.timeout:.2f}")
            log.info("发送超时：等待重发")
            # log.debug(f"increased timeout={atom.timeout:.2f}")
            if atom.text is None or len(atom.text) < (
                MAX_TEXT_LENGTH if atom.meth == "message" else CAPTION_LENGTH
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
        except AiogramError as e:
            self.exc_groups[feed].append(e)
            log.error("Uncaught AiogramError in send_%s.", atom.meth, exc_info=e)
        except BaseException as e:
            self.exc_groups[feed].append(e)
            log.error("Uncaught error in send_%s.", atom.meth, exc_info=e)
        return None

    def wait_all(self):
        tasks = [asyncio.create_task(i.wait()) for i in self.ch_feed.values()]
        if tasks:
            return asyncio.wait(tasks)
        return asyncio.sleep(0)
