"""This module split a feed into multiple atomic message."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Final, Generic, Protocol, Tuple, Type, overload

from aioqzone.type.entity import AtEntity, ConEntity, TextEntity
from aioqzone.utils.time import sementic_time
from aioqzone_feed.type import BaseFeed, FeedContent, VisualMedia
from pydantic import HttpUrl
from qqqr.utils.net import ClientAdapter
from telegram import InputMedia as _InputMedia
from telegram import InputMediaAnimation as Anim
from telegram import InputMediaDocument as Doc
from telegram import InputMediaPhoto as Pic
from telegram import InputMediaVideo as Video
from telegram import Message, ReplyMarkup
from typing_extensions import Self

from . import MD, BotProtocol, InputMedia

PIPE_OBJS = tuple[str, list[VisualMedia], list[bytes | None], list[Type[InputMedia]]]
LIM_TXT: Final = 4096
LIM_MD_TXT: Final = 1024
LIM_GROUP_MD: Final = 10

log = logging.getLogger(__name__)


class MsgPartial(ABC):
    """Message partial is the atomic unit to send/retry in sending progress.
    One feed can be seperated into more than one partials. One partial corresponds
    to one function call in aspect of behavior."""

    __slots__ = ("kwds", "meth")
    meth: str

    def __init__(self, **kw) -> None:
        self.kwds = kw

    @abstractmethod
    async def __call__(self, bot: BotProtocol, *args, **kwds) -> Message:
        """This means `send_xxx` in :class:`BotProtocol`."""
        pass

    @classmethod
    @abstractmethod
    def pipeline(
        cls,
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMedia],
        **kwds,
    ) -> Tuple[Self, PIPE_OBJS]:
        """Given a pipeline of texts, media metas, media raw, media types, this method
        pops up a fixed number of facts from pipeline and construct a new instance with these data.
        The rest of the pipeline is returned and can be passed to the next `pipeline`.

        :param txt: texts in pipeline, got from :meth:`stringify_entities`.
        :param metas: media metas in pipeline, got from feed medias.
        :param raws: media raw in pipeline, got from network (using url from corresponding media meta).
        :param md_types: media type, got from :meth:`LocalSplitter.guess_md_type`.
        """
        return cls(**kwds), (txt, metas, raws, md_types)

    @property
    def timeout(self) -> float:
        """Partial timeout. Since one partial is the atomic unit to send/retry in sending progress,
        every partial has its own timeout.
        """
        return self.kwds.get("timeout", 5.0)

    @timeout.setter
    def timeout(self, value: float):
        self.kwds["timeout"] = value

    @property
    def reply_markup(self) -> ReplyMarkup | None:
        """a common used keyword."""
        return self.kwds.get("reply_markup")

    @reply_markup.setter
    def reply_markup(self, value: ReplyMarkup | None):
        self.kwds["reply_markup"] = value


class TextPartial(MsgPartial):
    """Text partial represents a pure text message.
    Calling this will trigger :meth:`BotProtocol.send_message`.
    """

    __slots__ = ("text", "kwds")
    meth = "message"

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self.text = text

    async def __call__(self, bot: BotProtocol, *args, **kwds) -> Message:
        return await bot.send_message(*args, text=self.text, **(self.kwds | kwds))

    @classmethod
    def pipeline(
        cls,
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[Type[InputMedia]],
        **kwds,
    ) -> Tuple[Self, PIPE_OBJS]:
        return cls(txt[:LIM_TXT], **kwds), (txt[LIM_TXT:], metas, raws, md_types)


class MediaPartial(MsgPartial, Generic[MD]):
    """Media partial represents a message with **ONE** media. Each MediaPartial should have
    a :obj:`.meth` field which indicates what kind of media it contains. The meth is also used
    when MediaPartial is called. Thus "send_{meth}" must be a callable in :class:`BotProtocol`.
    """

    __slots__ = ("meta", "_raw", "text")

    def __init__(
        self,
        media: VisualMedia,
        raw: bytes | None,
        text: str | None = None,
        **kw,
    ) -> None:
        super().__init__(**kw)
        self.meta = media
        self._raw = raw
        self.text = text

    @property
    def content(self) -> bytes | str:
        """returns the media url or its raw data if :obj:`._raw` is not None."""
        return self._raw or str(self.meta.raw)

    def wrap_media(self, **kw) -> MD:
        """Build a :class:`~telegram.InputMedia` from a MediaPartial.
        This is used in :meth:`BotProtocol.edit_media`."""
        cls: Type[MD] = self.__orig_bases__[0].__args__[0]  # type: ignore
        if self.text:
            kw["caption"] = self.text
        return cls(
            media=self.content,
            **kw,
        )

    async def __call__(self, bot: BotProtocol, *args, **kwds) -> Message:
        f = getattr(bot, f"send_{self.meth}")
        return await f(*args, media=self.content, text=self.text, **(self.kwds | kwds))

    @classmethod
    def pipeline(
        cls,
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[Type[InputMedia]],
        **kwds,
    ) -> Tuple["MediaPartial", PIPE_OBJS]:
        cls = cls.query_subclass(md_types[0])
        return (
            cls(metas[0], raws[0], txt[:LIM_MD_TXT], **kwds),
            (txt[LIM_MD_TXT:], metas[1:], raws[1:], md_types[1:]),
        )

    # fmt: off
    @classmethod
    @overload
    def query_subclass(cls, ty: Type[Anim]) -> Type['AnimPartial']: ...
    @classmethod
    @overload
    def query_subclass(cls, ty: Type[Doc]) -> Type['DocPartial']: ...
    @classmethod
    @overload
    def query_subclass(cls, ty: Type[Pic]) -> Type['PicPartial']: ...
    @classmethod
    @overload
    def query_subclass(cls, ty: Type[Video]) -> Type['VideoPartial']: ...
    # fmt: on

    @classmethod
    def query_subclass(cls, ty):
        return {Anim: AnimPartial, Doc: DocPartial, Pic: PicPartial, Video: VideoPartial}[ty]


class AnimPartial(MediaPartial[Anim]):
    meth = "animation"

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


class DocPartial(MediaPartial[Doc]):
    meth = "document"


class PicPartial(MediaPartial[Pic]):
    meth = "photo"


class VideoPartial(MediaPartial[Video]):
    meth = "video"

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


class MediaGroupPartial(MsgPartial):
    """MediaGroupPartial represents a group of medias in one message. Calling this will trigger
    :meth:`BotProtocol.send_media_group`.
    """

    meth = "media_group"

    def __init__(self, text: str | None = None, **kw) -> None:
        super().__init__(**kw)
        self.text = text
        self.medias: list[InputMedia] = []

    @property
    def is_doc(self):
        """If the first media is Document.

        .. note:: If True, then any other medias in this partial **MUST** be document."""
        return isinstance(self.medias[0], Doc)

    @MsgPartial.reply_markup.getter
    def reply_markup(self):
        return None

    @reply_markup.setter
    def reply_markup(self, value: ReplyMarkup | None):
        assert value is None

    async def __call__(self, bot: BotProtocol, *args, **kwds) -> list[Message]:
        assert self.medias
        self.medias[0].caption = self.text  # type: ignore
        assert all(isinstance(i, _InputMedia) for i in self.medias)
        return await bot.send_media_group(*args, media=self.medias, **(self.kwds | kwds))

    def append(self, meta: VisualMedia, raw: bytes | None, cls: Type[InputMedia], **kw):
        """append a media into this partial."""
        assert issubclass(cls, _InputMedia)
        assert len(self.medias) < LIM_GROUP_MD
        self.medias.append(cls(media=raw or str(meta.raw), **kw))

    @classmethod
    def pipeline(
        cls,
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[Type[InputMedia]],
        **kwds,
    ) -> Tuple[Self, PIPE_OBJS]:
        """See :meth:`MsgPartial.pipeline`.

        .. note::

            If one media will be sent as a document, and not all of medias in this partial
            is document, this media will be sent as a link in caption, with a reason.
        """
        self = cls(**kwds)
        hint = ""
        for i in range(LIM_GROUP_MD):
            if not metas:
                break
            meta = metas.pop(0)
            raw = raws.pop(0)
            ty = md_types.pop(0)
            if ty is Doc and self.medias and not self.is_doc:
                if meta.is_video:
                    hint += f"P{i}: 不支持的视频格式，点击查看{href('原视频', meta.raw)}\n"
                else:
                    hint += f"P{i}: 图片过大无法发送/显示，点击查看{href('原图', meta.raw)}\n"
                continue
            self.append(meta, raw, ty)

        if hint:
            hint = "\n\n" + hint
        rest = LIM_MD_TXT - len(hint)

        self.text = txt[:rest] + hint
        return self, (txt[rest:], metas, raws, md_types)


def href(txt: str | int, url: str):
    return f"<a href='{url}'>{txt}</a>"


async def stringify_entities(entities: list[ConEntity] | None) -> str:
    """Stringify all entities and concatenate them.

    .. versionchanged:: 0.4.0a1.dev5

        changed to async-function for future improvement.
    """
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


def supported_video(url: HttpUrl):
    """Check if a video can be sent as video. (Telegram supports mp4 only)"""
    return bool(url.path and url.path.endswith(".mp4"))


def is_gif(b: bytes):
    """Check if a raw data is in gif format."""
    return b.startswith((b"47494638", b"GIF89a", b"GIF87a"))


class Splitter(Protocol):
    """A splitter is a protocol that ensure an object can do the following jobs:

    1. probe and transform `~aioqzone_feed.type.VisualMedia` into corresponding `~telegram.InputMedia`.
    2. Split a feed (and its possible forwardee) into multiple `.MsgPartial` and assign contents
    and medias into these partials according to telegram message size limit.

    """

    async def split(self, feed: FeedContent) -> tuple[list[MsgPartial], list[MsgPartial]]:
        """
        :param feed: feed to split into partials
        :return: (forward partials list, feed partials list)"""
        raise NotImplementedError


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
                if len(metas) > 1:
                    p, pipe_objs = MediaGroupPartial.pipeline(*pipe_objs)
                else:
                    p, pipe_objs = MediaPartial.pipeline(*pipe_objs)
            else:
                p, pipe_objs = TextPartial.pipeline(*pipe_objs)
            msgs.append(p)

        if isinstance(feed.forward, HttpUrl):
            # override disable_web_page_preview if forwarding an app.
            if isinstance(msgs[0], MediaGroupPartial):
                log.warning(f"Forward url and media coexist: {feed}")
            elif isinstance(msgs[0], TextPartial):
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

    def guess_md_type(self, media: VisualMedia | bytes) -> Type[InputMedia]:
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
            async with await self.client.get(str(media.raw)) as r:
                return b"".join([i async for i in r.aiter_bytes()])
        except:
            # give-up if error
            return

    def guess_md_type(self, media: VisualMedia | bytes) -> Type[InputMedia]:
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
