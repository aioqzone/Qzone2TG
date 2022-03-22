"""Telegram API has many limits. This module detects and solve these conflicts."""

import asyncio as aio
import logging
from collections import deque
from functools import partial
from time import time
from typing import Callable, TypeVar

from aiohttp import ClientSession
from aioqzone_feed.type import FeedContent
from async_timeout import timeout
from pydantic import HttpUrl
from telegram import Bot, InputFile, Message

from qzone3tg.utils.iter import countif, split_by_len

from . import BotProtocol, ChatId
from .atom import (
    LIM_GROUP_MD,
    LIM_MD_TXT,
    LIM_TXT,
    InputMedia,
    MediaMsg,
    MsgArg,
    PicMsg,
    Splitter,
    TextMsg,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


def to_task(args: list[MsgArg]) -> list[MsgArg | list[MediaMsg]]:
    """Group args, and associate each arg group with a operation name. The operation name
    is the method name in `.limitbot` (also in `telegram.bot`)"""

    md_num = countif(args, lambda a: isinstance(a, MediaMsg), initial=True)
    if md_num <= 1:
        return args  # type: ignore

    groups: list[list[MediaMsg]] = split_by_len(args[:md_num], LIM_GROUP_MD)
    return groups + args[md_num:]  # type: ignore


class BotTaskGenerator:
    bps: float = 2e6  # 2Mbps
    eps = bps

    def __init__(self, bot: Bot, splitter: Splitter):
        self.bot = bot
        self.splitter = splitter

    def estim_timeout(self, arg: MediaMsg) -> float:
        min_timeout = 10
        if isinstance(arg, PicMsg):
            min_timeout = 5
        if isinstance(arg.content, str):
            size = 1e7 if isinstance(arg, PicMsg) else 2e7
        else:
            size = len(arg.content)
        return max(min_timeout, size / self.bps)

    async def unify_send(self, feed: FeedContent):
        tasks = to_task(await self.splitter.split(feed))
        for group in tasks:
            yield self._get_partial(group)

    def _get_partial(self, arg: MsgArg | list[MediaMsg]):
        if isinstance(arg, list):
            if len(arg) > 1:
                timeout = sum(self.estim_timeout(i) for i in arg)
                return partial(
                    self.bot.send_media_group, media=[i.wrap_media() for i in arg], timeout=timeout
                )
            (arg,) = arg  # just unpack the single element

        match arg.meth:
            case "message":
                assert isinstance(arg, TextMsg)
                return partial(self.bot.send_message, text=arg.text)
            case "photo" | "video" | "animation" | "document":
                assert isinstance(arg, MediaMsg)
                kw = {arg.meth: arg.content, "timeout": self.estim_timeout(arg)}
                f: Callable[..., Message] = getattr(self.bot, f"send_{arg.meth}")
                return partial(f, caption=arg.text, **kw)
            case _:
                raise AttributeError(arg.meth)


class BotTaskEditter(BotTaskGenerator):
    def __init__(self, bot: Bot, splitter: Splitter, sess: ClientSession):
        super().__init__(bot, splitter)
        self.sess = sess

    async def edit_args(self, feed: FeedContent):
        for group in await self.splitter.split(feed):
            if isinstance(group, MediaMsg):
                yield group
                continue
            return

    async def force_bytes(self, call: partial[T]) -> partial[T]:
        _, meth = call.func.__name__.split("_", maxsplit=1)
        match meth:
            case "animation" | "document" | "photo" | "video":
                media = call.keywords.get(meth)
                if isinstance(media, bytes):
                    return call
                assert isinstance(media, str)
                logger.info(f"force fetch {meth}: {media}")
                async with self.sess.get(media) as r:
                    call.keywords[meth] = await r.content.read()
                return call
            case "media_group":
                media = call.keywords.get("media")
                assert isinstance(media, list)
                for i, im in enumerate(media):
                    media[i] = await self.force_bytes_inputmedia(im)
        return call

    async def force_bytes_inputmedia(self, media: InputMedia):
        if isinstance(media.media, InputFile) and isinstance(
            media.media.input_file_content, bytes
        ):
            return media

        assert isinstance(media.media, str)
        logger.info(f"force fetch {media.type}: {media.media}")
        async with self.sess.get(media.media) as r:
            media.media = InputFile(await r.content.read(), attach=True)
            return media

    def inc_timeout(self, call: partial[T]) -> partial[T]:
        org = call.keywords.get("timeout", 5)
        min_inc = 5
        _, meth = call.func.__name__.split("_", maxsplit=1)
        match meth:
            case "message":
                call.keywords["timeout"] = org + min_inc
                return call
            case "photo":
                content = call.keywords["photo"]
                size = 1e7 if isinstance(content, str) else len(content)
            case "animation" | "document" | "video":
                min_inc = 10
                content = call.keywords[meth]
                size = 2e7 if isinstance(content, str) else len(content)
            case "media_group":
                min_inc = len(call.keywords["media"]) * 5
                size = sum(self.estim_size_inputmedia(i) for i in call.keywords["media"])
            case _:
                raise ValueError
        timeout = max(org + min_inc, size / self.bps)
        call.keywords["timeout"] = timeout
        return call

    def estim_size_inputmedia(self, media: InputMedia) -> float:
        if isinstance(media.media, InputFile) and isinstance(
            media.media.input_file_content, bytes
        ):
            return len(media.media.input_file_content)

        if media.type == "photo":
            return 1e7
        return 2e7


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

    async def edit_message_media(self, to: ChatId, mid: int, media: InputMedia, **kw):
        f = partial(self.bot.edit_message_media, to, mid, media=media)
        async with self.sem.context():
            return await self._loop.run_in_executor(None, f)
