"""Telegram API has many limits. This module detects and solve these conflicts."""

import asyncio
import logging
from itertools import chain
from typing import Optional, Tuple, overload

from aioqzone_feed.type import FeedContent
from pydantic import HttpUrl
from qqqr.event import Emittable, Event
from qqqr.utils.net import ClientAdapter
from telegram import Bot, InputFile, Message

from . import BotProtocol, ChatId, GroupMedia, ReplyMarkup, SupportMedia
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

    def estim_size_inputmedia(self, media: SupportMedia) -> float:
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
                    async with self.client.get(media) as r:
                        call._raw = b"".join([i async for i in r.aiter_bytes()])
                except:
                    log.warning(f"force fetch error, skipped: {media}", exc_info=True)
                return call

            case "media_group":
                assert isinstance(call, MediaGroupPartial)
                for i, im in enumerate(call.medias):
                    call.medias[i] = await self.force_bytes_inputmedia(im)
        return call

    async def force_bytes_inputmedia(self, media: GroupMedia):
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
            async with self.client.get(media.media) as r:
                media = media.__class__(media=b"".join([i async for i in r.aiter_bytes()]))
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


class SemaBot(BotProtocol):
    """A implementation of :class:`BotProtocol` with content limitation checking and some type-casting.

    .. versionchanged:: 0.5.0a1

        Removed internal Semaphore. Use :class:`telegram.ext.BaseRateLimiter` instead.
    """

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_message(self, to: ChatId, text: str, **kw):
        assert len(text) <= LIM_TXT
        return await self.bot.send_message(to, text, **kw)

    async def send_photo(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) <= LIM_MD_TXT
        photo = media if isinstance(media, bytes) else str(media)
        return await self.bot.send_photo(to, photo, text, **kw)

    async def send_animation(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) <= LIM_MD_TXT
        anim = media if isinstance(media, bytes) else str(media)
        return await self.bot.send_animation(to, anim, caption=text, **kw)

    async def send_video(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) <= LIM_MD_TXT
        video = media if isinstance(media, bytes) else str(media)
        return await self.bot.send_video(to, video, caption=text, **kw)

    async def send_document(self, to: ChatId, media: HttpUrl | bytes, text: str, **kw):
        assert len(text) <= LIM_MD_TXT
        doc = media if isinstance(media, bytes) else str(media)
        return await self.bot.send_document(to, doc, text, **kw)

    async def edit_message_media(self, to: ChatId, mid: int, media: GroupMedia, **kw):
        return await self.bot.edit_message_media(media, to, mid, **kw)

    async def send_media_group(
        self, to: ChatId, media: list[GroupMedia], caption: str | None, **kw
    ) -> list[Message]:
        assert 0 < len(media) <= LIM_GROUP_MD
        assert len(getattr(media[0], "caption", None) or "") < LIM_MD_TXT
        return list(await self.bot.send_media_group(to, media, caption=caption, **kw))
