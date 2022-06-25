"""Telegram API has many limits. This module detects and solve these conflicts."""

import asyncio as aio
import logging
from collections import deque
from functools import partial
from itertools import chain
from time import time
from typing import Optional, Tuple, TypeVar, overload

from aioqzone_feed.type import FeedContent
from pydantic import HttpUrl
from qqqr.event import Emittable, Event
from qqqr.utils.net import ClientAdapter
from telegram import Bot, InputFile, Message, ReplyMarkup

from qzone3tg.utils.iter import countif, split_by_len

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

logger = logging.getLogger(__name__)
T = TypeVar("T")


class TaskerEvent(Event):
    async def reply_markup(
        self, feed: FeedContent
    ) -> Tuple[Optional[ReplyMarkup], Optional[ReplyMarkup]]:
        """:return: (forwardee reply_markup, feed reply_markup)."""
        return None, None


class BotTaskGenerator(Emittable[TaskerEvent]):
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
            yield self._get_partial(part)

    def _get_partial(self, arg: MsgPartial) -> MsgPartial:
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
        return arg


class BotTaskEditter(BotTaskGenerator):
    def __init__(self, splitter: Splitter, client: ClientAdapter):
        super().__init__(splitter)
        self.client = client

    async def media_args(self, feed: FeedContent):
        """Get media atoms of a feed."""
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
        match call.meth:
            case "animation" | "document" | "photo" | "video":
                assert isinstance(call, MediaPartial)
                media = call.content
                if isinstance(media, bytes):
                    return call
                assert isinstance(media, str)
                logger.info(f"force fetch {call.meth}: {media}")
                async with await self.client.get(media) as r:
                    call._raw = b"".join([i async for i in r.aiter_bytes()])
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

        assert isinstance(media.media, str)
        logger.info(f"force fetch {media.type}: {media.media}")
        async with await self.client.get(media.media) as r:
            media.media = InputFile(b"".join([i async for i in r.aiter_bytes()]), attach=True)
            return media

    def inc_timeout(self, call: MsgPartial) -> MsgPartial:
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
    def __init__(self, max_val: int) -> None:
        self.max = max_val
        self._loop = aio.get_event_loop()
        self._waiters = deque(maxlen=max_val)
        self.reset()

    def reset(self):
        self._val = self.max

    async def acquire(self, times: int = 1, *, block: bool = True):
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
        async def delay_release(end_time: float):
            await aio.sleep(end_time - time())
            self._val += times

        self._waiters.append(task := aio.create_task(delay_release(time() + 1)))
        task.add_done_callback(lambda t: self._waiters.remove(task))

    def context(self, times: int = 1):
        # fmt: off
        class ctx:
            __slots__ = ()
            async def __aenter__(*_): await self.acquire(times)
            async def __aexit__(*_): self.release(times)
        # fmt: on
        return ctx()


class SemaBot(BotProtocol):
    """A queue with convenient `send_*` methods for interacting purpose."""

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
        f = partial(self.bot.send_media_group, to, media=media, **kw)
        async with self.sem.context(len(media)):
            return await self._loop.run_in_executor(None, f)
