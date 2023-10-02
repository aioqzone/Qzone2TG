"""Splitters split a feed object into several atoms. They provide :meth:`~Splitter.unify_send` interface to split
a feed object into a chain of atom objects.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Sequence, overload

import qzemoji.utils as qeu
from aiogram.enums.input_media_type import InputMediaType
from aiogram.types.input_file import BufferedInputFile, InputFile
from aiogram.types.input_media_animation import InputMediaAnimation as Anim
from aiogram.types.input_media_document import InputMediaDocument as Doc
from aiogram.types.input_media_photo import InputMediaPhoto as Pic
from aiogram.types.input_media_video import InputMediaVideo as Video
from aiogram.utils.media_group import MediaType as GroupMedia
from aioqzone.model import AtEntity, ConEntity, EmEntity, LinkEntity, TextEntity
from aioqzone.utils.time import sementic_time
from aioqzone_feed.type import BaseFeed, FeedContent, VisualMedia
from httpx import URL
from pydantic import HttpUrl
from qqqr.utils.net import ClientAdapter

from .atom import MediaGroupPartial, MediaPartial, MsgPartial, TextPartial, href, url_basename

if TYPE_CHECKING:
    from . import SupportMedia


log = logging.getLogger(__name__)
html_trans = str.maketrans({"<": "&lt;", ">": "&gt;", "&": "&amp;"})


async def stringify_entities(entities: list[ConEntity] | None) -> str:
    """Stringify all entities and concatenate them.

    .. deprecated:: 0.4.0a1.dev5

        changed to async-function for future improvement.

    .. versionchanged:: 0.7.5.dev22

        support `~aioqzone.type.entity.LinkEntity`.
    """
    if not entities:
        return ""
    s = ""
    for e in entities:
        match e:
            case TextEntity():
                s += e.con.translate(html_trans)
            case AtEntity():
                s += f"@{href(e.nick.translate(html_trans), f'user.qzone.qq.com/{e.uin}')}"
            case LinkEntity():
                if isinstance(e.url, HttpUrl):
                    s += href(e.text, str(e.url))
                else:
                    s += f"{e.text}({e.url})"
            case EmEntity():
                s += await qeu.query_wrap(e.eid)
            case _:
                s += str(e.dict(exclude={"type"})).translate(html_trans)
    return s


def supported_video(url: str | URL):
    """Check if a video can be sent as video. (Telegram supports mp4 only)"""
    if isinstance(url, str):
        url = URL(url)
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
    async def split(self, feed: FeedContent) -> Sequence[MsgPartial]:
        """
        :param feed: feed to split into partials
        :return: a :class:`FeedPair` object containing atoms sequence."""
        raise NotImplementedError

    async def unify_send(self, feed: FeedContent) -> Sequence[MsgPartial]:
        """
        The unify_send function is a unified function to generate atomic unit to be sent.
        It will split the feed into multiple callable partials no matter
        what kind of media(s) the feed contains.

        :param feed:FeedContent: Pass the feed to the splitter
        :return: Message Partials. Forwardee partials is prior to forwarder partials.
        """

        if isinstance(feed.forward, FeedContent):
            a, b = await asyncio.gather(self.split(feed), self.split(feed.forward))
            return *a, *b
        return await self.split(feed)


class LocalSplitter(Splitter):
    """Local splitter do not due with network affairs. This means it cannot know what a media is exactly.
    It will guess the media type using its metadata.
    """

    async def split(self, feed: FeedContent) -> list[MsgPartial]:
        atoms: list[MsgPartial] = []

        txt = self.header(feed) + await stringify_entities(feed.entities)
        metas = feed.media or []
        probe_media = list(await asyncio.gather(*(self.probe(i) for i in metas)))
        md_types = [self.guess_md_type(i or m) for i, m in zip(probe_media, metas)]

        pipe_objs = (txt, metas, probe_media, md_types)

        while pipe_objs[0] or pipe_objs[1]:
            if pipe_objs[1]:
                if len(md_types) > 1 and (
                    (md_types[0] == InputMediaType.DOCUMENT) == (md_types[1] == Doc)
                ):
                    p, pipe_objs = MediaGroupPartial.pipeline(*pipe_objs)
                else:
                    p, pipe_objs = MediaPartial.pipeline(*pipe_objs)
            else:
                p, pipe_objs = TextPartial.pipeline(*pipe_objs)
            atoms.append(p)

        if isinstance(feed.forward, str):
            # override disable_web_page_preview if forwarding an app.
            match atoms[0]:
                case MediaGroupPartial():
                    log.warning(f"Forward url and media coexist: {feed}")
                case TextPartial():
                    atoms[0].kwds["disable_web_page_preview"] = False

        return atoms

    def header(self, feed: FeedContent) -> str:
        """Generate a header for a feed according to feed type.

        :param feed: feed to generate a header
        """
        semt = sementic_time(feed.abstime)
        uname = feed.nickname.translate(html_trans) or str(feed.uin)
        nickname = href(uname, f"user.qzone.qq.com/{feed.uin}")

        if feed.forward is None:
            return f"{nickname}{semt}发布了{href('说说', str(feed.unikey))}：\n\n"

        if isinstance(feed.forward, BaseFeed):
            return (
                f"{nickname}{semt}转发了"
                f"{href(feed.forward.nickname, f'user.qzone.qq.com/{feed.forward.uin}')}"
                f"的{href('说说', str(feed.unikey))}：\n\n"
            )
        elif isinstance(feed.forward, str):
            share = str(feed.forward)
            # here we ensure share url is the first url entity, so telegram's preview link feature
            # will fetch the app for user.
            return f"{uname}{semt}分享了{href('应用', share)}：\n\n"

        # should not send in <a> since it is not a valid url
        return f"{nickname}{semt}分享了应用: ({feed.forward})：\n\n"

    async def probe(self, media: VisualMedia, **kw) -> bytes | None:
        """:class:`LocalSpliter` does not probe any media."""
        return

    def guess_md_type(self, media: VisualMedia | bytes) -> InputMediaType:
        """Guess media type according to its metadata.

        :param media: metadata to guess
        """
        assert isinstance(media, VisualMedia)
        raw_url = URL(media.raw)
        if raw_url.path and raw_url.path.endswith(".gif"):
            return InputMediaType.ANIMATION
        if media.is_video:
            if supported_video(raw_url):
                return InputMediaType.VIDEO
            return InputMediaType.DOCUMENT
        if media.height + media.width > 1e4:
            return InputMediaType.DOCUMENT
        return InputMediaType.PHOTO


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
                return await r.content.read()
        except:
            # give-up if error
            log.warning("Error when probing", exc_info=True)
            return

    def guess_md_type(self, media: VisualMedia | bytes) -> InputMediaType:
        """Guess media type using media raw, otherwise by metadata.

        :param media: metadata to guess
        """
        if isinstance(media, VisualMedia):
            # super class handles VisualMedia well
            return super().guess_md_type(media)

        if len(media) > 5e7:
            return InputMediaType.DOCUMENT

        if is_gif(media):
            return InputMediaType.ANIMATION

        if len(media) > 1e7:
            return InputMediaType.DOCUMENT
        return InputMediaType.PHOTO

    async def media_args(self, feed: FeedContent):
        """Get media atoms of a feed.

        :param feed: the feed
        :return: media group partial or media partial.
        """
        if isinstance(feed.forward, FeedContent):
            feed = feed.forward
        for group in await self.split(feed):
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
        """This method will be called when a partial got :exc:`telegram.error.BadRequest` from aiogram.
        We will force fetch the url by ourself and send the raw data instead of the url to telegram.

        :param call: the partial that its media should be fetched.
        :return: The modified partial itself
        """
        match call.meth:
            case "animation" | "document" | "photo" | "video":
                assert isinstance(call, MediaPartial)
                media = call.content
                if isinstance(media, InputFile):
                    log.error("force fetch the raws")
                    return call

                log.info(f"force fetch a {call.meth}: {media}")
                try:
                    async with self.client.get(media) as r:
                        call._raw = BufferedInputFile(await r.content.read(), url_basename(media))
                except:
                    log.warning(f"force fetch error, skipped: {media}", exc_info=True)
                return call

            case "media_group":
                assert isinstance(call, MediaGroupPartial)
                for i, im in enumerate(call.builder._media):
                    call.builder._media[i] = await self.force_bytes_inputmedia(im)
        return call

    async def force_bytes_inputmedia(self, media: GroupMedia) -> GroupMedia:
        if isinstance(media.media, InputFile):
            return media

        if not isinstance(media.media, str):
            log.warning(
                f"InputMedia is called force_bytes but its media is not url: {media.media}"
            )
            return media

        log.info(f"force fetch {media.type}: {media.media}")
        try:
            async with self.client.get(media.media) as r:
                media = media.__class__(
                    media=BufferedInputFile(await r.content.read(), url_basename(media.media))
                )
        except:
            log.warning(f"force fetch error, skipped: {media.media}", exc_info=True)
        return media
