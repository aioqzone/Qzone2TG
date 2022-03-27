"""This module split a feed into multiple atomic message."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Type, TypeVar

from aiohttp import ClientSession
from aioqzone.type.entity import AtEntity, ConEntity, TextEntity
from aioqzone.utils.time import sementic_time
from aioqzone_feed.type import BaseFeed, FeedContent, VisualMedia
from pydantic import HttpUrl
from telegram import InputMediaAnimation as Anim
from telegram import InputMediaDocument as Doc
from telegram import InputMediaPhoto as Pic
from telegram import InputMediaVideo as Video

from qzone3tg.utils.iter import split_by_len

from . import InputMedia

MD = TypeVar("MD", bound=InputMedia)
LIM_TXT = 4096
LIM_MD_TXT = 1024
LIM_GROUP_MD = 10


class MsgArg:
    __slots__ = ("kw", "meth")
    meth: str

    def __init__(self, **kw) -> None:
        self.kw = kw


@dataclass
class TextMsg(MsgArg):
    __slots__ = ("text",)
    meth = "message"

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self.text = text


@dataclass
class MediaMsg(MsgArg, Generic[MD]):
    __slots__ = ("meta", "_raw", "text")

    def __init__(
        self,
        media: VisualMedia,
        raw: bytes | VisualMedia,
        text: str | None = None,
        **kw,
    ) -> None:
        super().__init__(**kw)
        self.meta = media
        self._raw = raw if isinstance(raw, bytes) else None
        self.text = text

    @property
    def content(self) -> bytes | str:
        return self._raw or str(self.meta.raw)

    def wrap_media(self, **kw) -> MD:
        return self.__orig_bases__[0].__args__[0](  # type: ignore
            media=self.content,
            caption=self.text,
            **kw,
        )


class AnimMsg(MediaMsg[Anim]):
    meth = "animation"

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


class DocMsg(MediaMsg[Doc]):
    meth = "document"


class PicMsg(MediaMsg[Pic]):
    meth = "photo"


class VideoMsg(MediaMsg[Video]):
    meth = "video"

    def wrap_media(self, **kw) -> Video:
        return super().wrap_media(thumb=self.thumb, **kw)

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


def href(txt: str, url: str):
    return f"<a href='{url}'>{txt}</a>"


def supported_video(url: HttpUrl):
    """Telegram supports mp4 only."""
    return bool(url.path and url.path.endswith(".mp4"))


def is_gif(b: bytes):
    return b.startswith((b"47494638", b"GIF89a", b"GIF87a"))


class Splitter(ABC):
    @abstractmethod
    async def split(self, feed: FeedContent) -> tuple[list[MsgArg], list[MsgArg]]:
        """:return: (forward msg list, feed msg list)"""
        pass


class LocalSplitter(Splitter):
    def stringify_entities(self, entities: list[ConEntity] | None) -> str:
        if not entities:
            return ""
        s = ""
        for e in entities:
            if isinstance(e, TextEntity):
                s += e.con
            elif isinstance(e, AtEntity):
                s += f"@{href(e.nick, f'user.qzone.qq.com/{e.uin}')}"
            else:
                s += str(e.dict(exclude={"type"}))
        return s

    async def split(self, feed: FeedContent) -> tuple[list[MsgArg], list[MsgArg]]:
        msgs: list[MsgArg] = []
        fmsg = []
        # send forward before stem message
        if isinstance(feed.forward, FeedContent):
            fmsg = (await self.split(feed.forward))[1]

        alltext = self.header(feed) + self.stringify_entities(feed.entities)

        # no media, send as text message
        if not feed.media:
            msgs += [TextMsg(i) for i in split_by_len(alltext, LIM_TXT)]
            return fmsg, msgs

        media = [await self.probe(i) for i in feed.media]
        first_md = media[0]
        if len(media) == 1:
            # only one media to be sent
            cls = await self.probe_md_type(first_md)
            msgs.append(cls(feed.media[0], first_md, alltext[:LIM_MD_TXT]))
            msgs += [TextMsg(i) for i in split_by_len(alltext[LIM_MD_TXT:], LIM_TXT)]
            return fmsg, msgs

        cur = len(msgs)  # attach caption to this msg
        md_clss = [await self.probe_md_type(i) for i in media]
        # document must not mixed with other types
        if all(i is DocMsg for i in md_clss) == any(i is DocMsg for i in md_clss):
            msgs += [cls(vm, m) for cls, vm, m in zip(md_clss, feed.media, media)]
            return fmsg, self.__merge_text_into_media_ls(msgs, alltext, cur)

        alltext += "\n\n"
        for i, (cls, vm, m) in enumerate(zip(md_clss, feed.media, media), start=1):
            # attach link directly in text
            if cls is DocMsg:
                if vm.is_video:
                    alltext += f"P{i}：不支持的视频格式，点击查看{href('原视频', vm.raw)}😅"
                else:
                    alltext += f"P{i}：图片过大无法发送/显示，点击查看{href('原图', vm.raw)}😅"
                continue
            # otherwise send the media
            msgs.append(cls(vm, m))

        return fmsg, self.__merge_text_into_media_ls(msgs, alltext, cur)

    def __merge_text_into_media_ls(self, msgs: list[MsgArg], text: str, start: int = 0):
        # insert text into group heads
        passages = split_by_len(text, LIM_MD_TXT)
        for i in range(start, len(msgs), LIM_GROUP_MD):
            if not passages:
                continue
            assert isinstance(a := msgs[i], MediaMsg)
            a.text = passages.pop(0)
        msgs += [TextMsg(i) for i in passages]
        return msgs

    def header(self, feed: FeedContent) -> str:
        semt = sementic_time(feed.abstime)
        nickname = href(feed.nickname, f"user.qzone.qq.com/{feed.uin}")

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

    async def probe(self, media: VisualMedia, **kw) -> VisualMedia | bytes:
        """`LocalSpliter` do not probe."""
        return media

    async def probe_md_type(self, media: VisualMedia | bytes) -> Type[MediaMsg]:
        assert isinstance(media, VisualMedia)
        if media.is_video:
            if supported_video(media.raw):
                return VideoMsg
            return DocMsg
        if media.height + media.width > 1e4:
            return DocMsg
        if media.raw.path and media.raw.path.endswith(".gif"):
            return AnimMsg
        return PicMsg


class FetchSplitter(LocalSplitter):
    """Fetch splitter has the right to fetch raw content of an url from network to make a
    more precise predict."""

    def __init__(self, sess: ClientSession) -> None:
        super().__init__()
        self.sess = sess

    async def probe(self, media: VisualMedia) -> VisualMedia | bytes:
        if media.is_video:
            return media  # video is too large to get
        if media.height + media.width > 1e4:
            return media  # media is too large, it will be sent as document/link

        # fetch the media to probe correctly
        async with self.sess.get(str(media.raw)) as r:
            return await r.content.read()

    async def probe_md_type(self, media: VisualMedia | bytes) -> Type[MediaMsg]:
        if isinstance(media, VisualMedia):
            # super class handles VisualMedia well
            return await super().probe_md_type(media)

        if len(media) > 5e7:
            return DocMsg

        if is_gif(media):
            return AnimMsg

        if len(media) > 1e7:
            return DocMsg
        return PicMsg
