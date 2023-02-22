"""Splitters split a feed object into several atoms. They provide :meth:`~Splitter.unify_send` interface to split
a feed object into a chain of atom objects.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Sequence, overload

from aioqzone.type.entity import AtEntity, ConEntity, TextEntity
from aioqzone.utils.time import sementic_time
from aioqzone_feed.type import BaseFeed, FeedContent, VisualMedia
from pydantic import HttpUrl
from qqqr.utils.net import ClientAdapter
from telegram import InputFile
from telegram import InputMediaAnimation as Anim
from telegram import InputMediaDocument as Doc
from telegram import InputMediaPhoto as Pic
from telegram import InputMediaVideo as Video
from telegram.constants import MediaGroupLimit

from .atom import MediaGroupPartial, MediaPartial, MsgPartial, PicPartial, TextPartial, href

if TYPE_CHECKING:
    from . import GroupMedia, SupportMedia


log = logging.getLogger(__name__)


async def stringify_entities(entities: list[ConEntity] | None) -> str:
    """Stringify all entities and concatenate them.

    .. versionchanged:: 0.4.0a1.dev5

        changed to async-function for future improvement.
    """
    if not entities:
        return ""
    s = ""
    for e in entities:
        match e:
            case TextEntity():
                s += e.con
            case AtEntity():
                s += f"@{href(e.nick, f'user.qzone.qq.com/{e.uin}')}"
            case _:
                s += str(e.dict(exclude={"type"}))
    return s


def supported_video(url: HttpUrl):
    """Check if a video can be sent as video. (Telegram supports mp4 only)"""
    return bool(url.path and url.path.endswith(".mp4"))


def is_gif(b: bytes):
    """Check if a raw data is in gif format."""
    return b.startswith((b"47494638", b"GIF89a", b"GIF87a"))


class Splitter(ABC):
    """A splitter is a protocol that ensure an object can do the following jobs:

    1. probe and transform `~aioqzone_feed.type.VisualMedia` into corresponding `~telegram.InputMedia`.
    2. Split a feed (and its possible forwardee) into multiple `.MsgPartial` and assign contents
    and medias into these partials according to telegram message size limit.

    """

    @abstractmethod
    async def split(self, feed: FeedContent) -> tuple[Sequence[MsgPartial], Sequence[MsgPartial]]:
        """
        :param feed: feed to split into partials
        :return: (forward partials Sequence, feed partials Sequence)"""
        raise NotImplementedError

    async def unify_send(self, feed: FeedContent):
        """
        The unify_send function is a unified function to generate atomic unit to be sent.
        It will split the feed into multiple callable partials no matter
        what kind of media(s) the feed contains.

        :param feed:FeedContent: Pass the feed to the splitter
        :return: Message Partials. Forwardee partials is prior to forwarder partials.
        """

        fw, fe = await self.split(feed)
        return (*fw, *fe)


class LocalSplitter(Splitter):
    """Local splitter do not due with network affairs. This means it cannot know what a media is exactly.
    It will guess the media type using its metadata.
    """

    async def split(self, feed: FeedContent) -> tuple[list[MsgPartial], list[MsgPartial]]:
        msgs: list[MsgPartial] = []

        txt = self.header(feed) + await stringify_entities(feed.entities)
        metas = feed.media or []
        probe_media = list(await asyncio.gather(*(self.probe(i) for i in metas)))
        md_types = [self.guess_md_type(i or m) for i, m in zip(probe_media, metas)]

        pipe_objs = (txt, metas, probe_media, md_types)

        while pipe_objs[0] or pipe_objs[1]:
            if pipe_objs[1]:
                if len(md_types) > 1 and (
                    issubclass(md_types[0], Doc) == issubclass(md_types[1], Doc)
                ):
                    p, pipe_objs = MediaGroupPartial.pipeline(*pipe_objs)
                else:
                    p, pipe_objs = MediaPartial.pipeline(*pipe_objs)
            else:
                p, pipe_objs = TextPartial.pipeline(*pipe_objs)
            msgs.append(p)

        if isinstance(feed.forward, HttpUrl):
            # override disable_web_page_preview if forwarding an app.
            match msgs[0]:
                case MediaGroupPartial():
                    log.warning(f"Forward url and media coexist: {feed}")
                case TextPartial():
                    msgs[0].kwds["disable_web_page_preview"] = False

        # send forward before stem message
        if isinstance(feed.forward, FeedContent):
            fmsg = (await self.split(feed.forward))[1]
        else:
            fmsg = []

        return fmsg, msgs

    def header(self, feed: FeedContent) -> str:
        """Generate a header for a feed according to feed type.

        :param feed: feed to generate a header
        """
        semt = sementic_time(feed.abstime)
        nickname = href(feed.nickname or feed.uin, f"user.qzone.qq.com/{feed.uin}")

        if feed.forward is None:
            return f"{nickname}{semt}发布了{href('说说', str(feed.unikey))}：\n\n"

        if isinstance(feed.forward, BaseFeed):
            return (
                f"{nickname}{semt}转发了"
                f"{href(feed.forward.nickname, f'user.qzone.qq.com/{feed.forward.uin}')}"
                f"的{href('说说', str(feed.unikey))}：\n\n"
            )
        elif isinstance(feed.forward, HttpUrl):
            share = str(feed.forward)
            return f"{nickname}{semt}分享了{href('应用', share)}：\n\n"

        # should not send in <a> since it is not a valid url
        return f"{nickname}{semt}分享了应用: ({feed.forward})：\n\n"

    async def probe(self, media: VisualMedia, **kw) -> bytes | None:
        """:class:`LocalSpliter` does not probe any media."""
        return

    def guess_md_type(self, media: VisualMedia | bytes) -> type[SupportMedia]:
        """Guess media type according to its metadata.

        :param media: metadata to guess
        """
        assert isinstance(media, VisualMedia)
        if media.is_video:
            if supported_video(media.raw):
                return Video
            return Doc
        if media.height + media.width > 1e4:
            return Doc
        if media.raw.path and media.raw.path.endswith(".gif"):
            return Anim
        return Pic


class FetchSplitter(LocalSplitter):
    """Fetch splitter has the right to fetch raw content of an url from network to make a
    more precise predict.
    """

    def __init__(self, client: ClientAdapter) -> None:
        super().__init__()
        self.client = client

    async def probe(self, media: VisualMedia) -> bytes | None:
        """:meth:`FetchSplitter.probe` will fetch the media from remote.

        :param media: metadata to fetch
        """

        if media.is_video:
            return  # video is too large to get
        if media.height + media.width > 1e4:
            return  # media is too large, it will be sent as document/link

        try:
            # fetch the media to probe correctly
            async with self.client.get(str(media.raw)) as r:
                return b"".join([i async for i in r.aiter_bytes()])
        except:
            # give-up if error
            log.warning("Error when probing", exc_info=True)
            return

    def guess_md_type(self, media: VisualMedia | bytes) -> type[SupportMedia]:
        """Guess media type using media raw, otherwise by metadata.

        :param media: metadata to guess
        """
        if isinstance(media, VisualMedia):
            # super class handles VisualMedia well
            return super().guess_md_type(media)

        if len(media) > 5e7:
            return Doc

        if is_gif(media):
            return Anim

        if len(media) > 1e7:
            return Doc
        return Pic

    async def media_args(self, feed: FeedContent):
        """Get media atoms of a feed.

        :param feed: the feed
        :return: media group partial or media partial.
        """
        if isinstance(feed.forward, FeedContent):
            feed = feed.forward
        for group in (await self.split(feed))[1]:
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

    # fmt: off
    @overload
    async def force_bytes_inputmedia(self, media: GroupMedia) -> GroupMedia: ...
    @overload
    async def force_bytes_inputmedia(self, media: SupportMedia) -> SupportMedia: ...
    # fmt: true

    async def force_bytes_inputmedia(self, media: SupportMedia) -> SupportMedia:
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
                media = media.__class__(media=r.content)
        except:
            log.warning(f"force fetch error, skipped: {media.media}", exc_info=True)
        return media
