"""Telegram API has many limits. This module detects and solve these conflicts."""

import asyncio
import logging
from collections import deque
from functools import partial
from itertools import chain
from time import time
from typing import Optional, Tuple, overload

from aioqzone_feed.type import FeedContent
from pydantic import HttpUrl
from qqqr.event import Emittable, Event
from qqqr.utils.net import ClientAdapter
from telegram import Bot, InputFile, Message, ReplyMarkup

from . import BotProtocol, ChatId, InputMedia
from .atom import (
    LIM_GROUP_MD,
    LIM_MD_TXT,
    LIM_TXT,
    MediaGroupPartial,
    MediaPartial,
    MsgPartial,
    PicPartial,
    Splitter,
    TextPartial,
)

log = logging.getLogger(__name__)


class TaskerEvent(Event):
    async def reply_markup(
        self, feed: FeedContent
    ) -> Tuple[Optional[ReplyMarkup], Optional[ReplyMarkup]]:
        """Allow app to generate reply_markup according to its own policy.

        :param feed: the feed to generate reply_markup
        :return: (forwardee reply_markup, feed reply_markup)."""
        return None, None


class BotTaskGenerator(Emittable[TaskerEvent]):
    """:class:`BotTaskGenerator` is the middleware between Splitter and Sending Queue.
    It will post-process partials from splitter and return them to the queue.

    The post process includes estimating and adding timeout, adding reply_markup, etc.
    """

    bps: float = 2e6  # 2Mbps
    eps = bps

    def __init__(self, splitter: Splitter):
        self.splitter = splitter

    def estim_timeout(self, arg: MediaPartial) -> float:
        min_timeout = 10
        if isinstance(arg, PicPartial):
            min_timeout = 5
        if isinstance(arg.content, str):
            size = 1e7 if isinstance(arg, PicPartial) else 2e7
        else:
            size = len(arg.content)
        return max(min_timeout, size / self.bps)

    def estim_size_inputmedia(self, media: InputMedia) -> float:
        if isinstance(media.media, InputFile) and isinstance(
            media.media.input_file_content, bytes
        ):
            return len(media.media.input_file_content)

        if media.type == "photo":
            return 1e7
        return 2e7

    async def unify_send(self, feed: FeedContent):
        """
        The unify_send function is a unified function to generate atomic unit to be sent.
        It will split the feed into multiple callable partials no matter
        what kind of media(s) the feed contains.

        :param feed:FeedContent: Pass the feed to the splitter
        :return: Message Partials. Forwardee partials is prior to forwarder partials.
        """

        tasks = await self.splitter.split(feed)
        for mkup, part in zip(await self.hook.reply_markup(feed), tasks):
            if mkup is None:
                continue
            for part in part:
                if isinstance(part, MediaGroupPartial):
                    continue
                part.reply_markup = mkup
                break

        for part in chain(*tasks):
            self._set_timeout(part)
            yield part

    def _set_timeout(self, arg: MsgPartial) -> None:
        """Estimate and set timeout for each partial that contains media.

        :param arg: partial to be set timeout. :class:`TextPartial` will be returned unchanged.
        :class:`MediaPartial` and :class:`MediaGroupPartial` will got a timeout keyword."""
        match arg.meth:
            case "message":
                assert isinstance(arg, TextPartial)
            case "photo" | "video" | "animation" | "document":
                assert isinstance(arg, MediaPartial)
                arg.timeout = self.estim_timeout(arg)
            case "media_group":
                assert isinstance(arg, MediaGroupPartial)
                size = sum(self.estim_size_inputmedia(i) for i in arg.medias)
                arg.timeout = max(len(arg.medias) * 5, size / self.bps)
            case _:
                raise AttributeError(arg.meth)


class BotTaskEditter(BotTaskGenerator):
    """Besides processes mentioned in :class:`BotTaskGenerator`,
    :class:`BotTaskEditter` includes methods to edit an existing partial if needed.
    """

    def __init__(self, splitter: Splitter, client: ClientAdapter):
        super().__init__(splitter)
        self.client = client

    async def media_args(self, feed: FeedContent):
        """Get media atoms of a feed.

        :param feed: the feed
        :return: media group partial or media partial.
        """
        if isinstance(feed.forward, FeedContent):
            feed = feed.forward
        for group in (await self.splitter.split(feed))[1]:
            if isinstance(group, (MediaPartial, MediaGroupPartial)):
                yield group
                continue
            return

    # fmt: off
    @overload
    async def force_bytes(self, call: MediaPartial) -> MediaPartial: ...
    @overload
    async def force_bytes(self, call: MediaGroupPartial) -> MediaGroupPartial: ...
    # fmt: on

    async def force_bytes(self, call: MsgPartial) -> MsgPartial:
        """This method will be called when a partial got :exc:`telegram.error.BadRequest` from telegram.
        We will force fetch the url by ourself and send the raw data instead of the url to telegram.

        :param call: the partial that its media should be fetched.
        :return: The modified partial itself
        """
        match call.meth:
            case "animation" | "document" | "photo" | "video":
                assert isinstance(call, MediaPartial)
                media = call.content
                if isinstance(media, bytes):
                    log.error("force fetch the raws")
                    return call

                log.info(f"force fetch a {call.meth}: {media}")
                try:
                    async with await self.client.get(media) as r:
                        call._raw = b"".join([i async for i in r.aiter_bytes()])
                except:
                    log.warning(f"force fetch error, skipped: {media}", exc_info=True)
                return call

            case "media_group":
                assert isinstance(call, MediaGroupPartial)
                for i, im in enumerate(call.medias):
                    call.medias[i] = await self.force_bytes_inputmedia(im)
        return call

    async def force_bytes_inputmedia(self, media: InputMedia):
        if isinstance(media.media, InputFile) and isinstance(
            media.media.input_file_content, bytes
        ):
            return media

        if not isinstance(media.media, str):
            log.warning(
                f"InputMedia is called force_bytes but its media is not url: {media.media}"
            )
            return media

        log.info(f"force fetch {media.type}: {media.media}")
        try:
            async with await self.client.get(media.media) as r:
                media.media = InputFile(b"".join([i async for i in r.aiter_bytes()]), attach=True)
        except:
            log.warning(f"force fetch error, skipped: {media.media}", exc_info=True)
        return media

    def inc_timeout(self, call: MsgPartial) -> MsgPartial:
        """
        The inc_timeout function takes a atomic unit and increases its timeout
        to account for network latency.

        :param call: The partial which timeout is to be increase
        :return: The modified partial itself
        """

        org = call.timeout
        min_inc = 5
        match call.meth:
            case "message":
                call.timeout = org + min_inc
                return call
            case "photo":
                assert isinstance(call, PicPartial)
                size = 1e7 if isinstance(call.content, str) else len(call.content)
            case "animation" | "document" | "video":
                assert isinstance(call, MediaPartial)
                min_inc = 10
                size = 2e7 if isinstance(call.content, str) else len(call.content)
            case "media_group":
                assert isinstance(call, MediaGroupPartial)
                min_inc = len(call.medias) * 5
                size = sum(self.estim_size_inputmedia(i) for i in call.medias)
            case _:
                raise ValueError
        timeout = max(org + min_inc, size / self.bps)
        call.timeout = timeout
        return call


class RelaxSemaphore:
    """A rate-limiter implemented just like :class:`asyncio.Semaphore`, except:

    - You can :meth:`.acquire` or :meth:`.release` multiple times at the same time.
    - :meth:`.release` will not "release" at once. It will delay one second.
    """

    def __init__(self, max_val: int) -> None:
        self.max = self._val = max_val
        self._loop = asyncio.get_event_loop()
        self._waiters = deque(maxlen=max_val)
        self.reset()

    def reset(self):
        """reset to initial state."""
        self._val = self.max
        self._waiters.clear()

    async def acquire(self, times: int = 1, *, block: bool = True):
        """Like :meth:`asyncio.Semaphore.acquire`. But can be acquired multiple times
        in one call.

        :param times: acquire times.
        :param block: if False, will not block current coro. but returns False.
        If True, block current coro. and always returns True. Default as True.
        """
        if self._val >= times:
            # accept
            self._val -= times
            return True
        if not block:
            return False
        assert self.max >= times
        while self._val < times:
            # wait for release
            task = self._waiters.popleft()
            await task
        self._val -= times
        return True

    def release(self, times: int = 1) -> None:
        """Release given times after one second."""

        async def delay_release(end_time: float):
            await asyncio.sleep(end_time - time())
            self._val += times

        self._waiters.append(task := asyncio.create_task(delay_release(time() + 1)))
        # BUG: task not in waiters?
        task.add_done_callback(lambda _: task in self._waiters and self._waiters.remove(task))

    def context(self, times: int = 1):
        """Returns a context manager which acquire semaphore `times` times when enter, and
        release `times` times when exit. Example:

        >>> await sem.acqure(times)
        >>> try: ...
        >>> except: sem.release(times)

        Code above can be simplified as:

        >>> async with sem.context(times): ...
        """

        # fmt: off
        class ctx:
            __slots__ = ()
            async def __aenter__(*_): await self.acquire(times)
            async def __aexit__(*_): self.release(times)
        # fmt: on
        return ctx()


class SemaBot(BotProtocol):
    """A implementation of :class:`BotProtocol` using :class:`telegram.Bot` with built-in
    rate-limiter (:class:`RelaxSemaphore`)."""

    def __init__(self, bot: Bot, sem: RelaxSemaphore) -> None:
        self.bot = bot
        self.sem = sem
        self._loop = self.sem._loop

    async def send_message(self, to: ChatId, text: str, **kw):
        assert len(text) < LIM_TXT
        f = partial(self.bot.send_message, to, text, **kw)
        async with self.sem.context():
            return await self._loop.run_in_executor(None, f)

    async def send_photo(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) < LIM_MD_TXT
        photo = media if isinstance(media, bytes) else str(media)
        f = partial(self.bot.send_photo, to, photo, text, **kw)
        async with self.sem.context():
            return await self._loop.run_in_executor(None, f)

    async def send_animation(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) < LIM_MD_TXT
        anim = media if isinstance(media, bytes) else str(media)
        f = partial(self.bot.send_animation, to, anim, caption=text, **kw)
        async with self.sem.context():
            return await self._loop.run_in_executor(None, f)

    async def send_video(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) < LIM_MD_TXT
        video = media if isinstance(media, bytes) else str(media)
        f = partial(self.bot.send_video, to, video, caption=text, **kw)
        async with self.sem.context():
            return await self._loop.run_in_executor(None, f)

    async def send_document(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) < LIM_MD_TXT
        doc = media if isinstance(media, bytes) else str(media)
        f = partial(self.bot.send_document, to, doc, caption=text, **kw)
        async with self.sem.context():
            return await self._loop.run_in_executor(None, f)

    async def edit_message_media(self, to: ChatId, mid: int, media: InputMedia, **kw):
        f = partial(self.bot.edit_message_media, to, mid, media=media, **kw)
        async with self.sem.context():
            return await self._loop.run_in_executor(None, f)

    async def send_media_group(self, to: ChatId, media: list[InputMedia], **kw) -> list[Message]:
        assert len(media) < LIM_GROUP_MD
        f = partial(self.bot.send_media_group, to, media=media, **kw)
        async with self.sem.context(len(media)):
            return await self._loop.run_in_executor(None, f)
