"""This module split a feed into multiple atomic message."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Self, Sequence

from aiogram import Bot
from aiogram.enums import InputMediaType
from aiogram.types import BufferedInputFile, Message
from aiogram.utils.formatting import Text, TextLink, as_list
from aiogram.utils.media_group import MediaGroupBuilder
from aioqzone_feed.type import VisualMedia

from . import *

PIPE_OBJS = tuple[Text, list[VisualMedia], list[bytes | None], list[InputMediaType]]


log = logging.getLogger(__name__)


def url_basename(url: str):
    return url[url.rfind("/") + 1 :]


class MsgAtom(ABC):
    """Message atom is the atomic unit to send/retry in sending progress.
    One feed can be seperated into more than one atoms. One atom corresponds
    to one function call in aspect of behavior."""

    __slots__ = ("kwds", "meth", "text")
    meth: ClassVar[str]
    text: Text | None

    def __init__(self, **kw) -> None:
        self.kwds = kw

    @abstractmethod
    async def __call__(self, bot: Bot, *args, **kwds) -> Message | Sequence[Message]:
        """This means `send_xxx` in :class:`Bot`."""
        pass

    @classmethod
    @abstractmethod
    def pipeline(
        cls,
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMediaType],
        **kwds,
    ) -> tuple[Self, PIPE_OBJS]:
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
        """Partial timeout. Since one atom is the atomic unit to send/retry in sending progress,
        every atom has its own timeout.
        """
        return self.kwds.get("read_timeout", 5.0)

    @timeout.setter
    def timeout(self, value: float):
        self.kwds["write_timeout"] = value
        self.kwds["read_timeout"] = value

    @property
    def reply_markup(self) -> ReplyMarkup | None:
        """a common used keyword."""
        return self.kwds.get("reply_markup")

    @reply_markup.setter
    def reply_markup(self, value: ReplyMarkup | None):
        self.kwds["reply_markup"] = value

    @property
    def reply_to_message_id(self) -> int | None:
        return self.kwds.get("reply_to_message_id")

    @reply_to_message_id.setter
    def reply_to_message_id(self, i: Message | int | None):
        match i:
            case Message():
                self.kwds["reply_to_message_id"] = i.message_id
            case _:
                self.kwds["reply_to_message_id"] = i


class TextAtom(MsgAtom):
    """Text atom represents a pure text message.
    Calling this will trigger :meth:`Bot.send_message`.
    """

    meth = "message"

    def __init__(self, text: Text, **kw) -> None:
        super().__init__(**kw)
        self.text = text

    async def __call__(self, bot: Bot, *args, **kwds) -> Message:
        assert self.text
        return await bot.send_message(*args, **self.text.as_kwargs(), **(self.kwds | kwds))

    @classmethod
    def pipeline(
        cls,
        txt: Text,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMediaType],
        **kwds,
    ) -> tuple[Self, PIPE_OBJS]:
        return cls(txt[:LIM_TXT], **kwds), (txt[LIM_TXT:], metas, raws, md_types)


class MediaAtom(MsgAtom):
    """MediaAtom represents a message with **ONE** media. Each MediaPartial should have
    a :obj:`.meth` field which indicates what kind of media it contains. The meth is also used
    when MediaPartial is called. Thus "send_{meth}" must be a callable in :class:`Bot`.
    """

    __slots__ = ("meta", "_raw", "__md_cls__")
    __md_cls__: ClassVar[type[SupportMedia]]
    meth: ClassVar[str]

    def __init__(
        self,
        media: VisualMedia,
        raw: bytes | None,
        text: Text | None = None,
        **kw,
    ) -> None:
        super().__init__(**kw)
        self.meta = media
        self._raw = BufferedInputFile(raw, url_basename(media.raw)) if raw else None
        self.text = text

    @property
    def content(self) -> BufferedInputFile | str:
        """returns the media url or its raw data if :obj:`._raw` is not None."""
        return self._raw or self.meta.raw

    async def __call__(self, bot: Bot, *args, **kwds) -> Message:
        f = getattr(bot, f"send_{self.meth}")
        kwds[self.meth] = self.content
        if self.text:
            kwds.update(self.text.as_kwargs(text_key="caption"))
        return await f(*args, **(self.kwds | kwds))

    @classmethod
    def pipeline(
        cls,
        txt: Text,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMediaType],
        **kwds,
    ) -> tuple["MediaAtom", PIPE_OBJS]:
        cls = InputMedia2Partial[md_types[0]]

        return (
            cls(metas[0], raws[0], txt[:LIM_MD_TXT], **kwds),
            (txt[LIM_MD_TXT:], metas[1:], raws[1:], md_types[1:]),
        )


class AnimAtom(MediaAtom):
    meth = "animation"
    __md_cls__ = InputMediaAnimation

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


class DocAtom(MediaAtom):
    meth = "document"
    __md_cls__ = InputMediaDocument


class PicAtom(MediaAtom):
    meth = "photo"
    __md_cls__ = InputMediaPhoto


class VideoAtom(MediaAtom):
    meth = "video"
    __md_cls__ = InputMediaVideo

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


InputMedia2Partial = {
    InputMediaType.ANIMATION: AnimAtom,
    InputMediaType.DOCUMENT: DocAtom,
    InputMediaType.PHOTO: PicAtom,
    InputMediaType.VIDEO: VideoAtom,
}


class MediaGroupAtom(MsgAtom):
    """MediaGroupPartial represents a group of medias in one message. Calling this will trigger
    :meth:`Bot.send_media_group`.
    """

    meth = "media_group"
    is_doc: bool | None = None
    """If the first media is Document.

        .. note:: If True, then any other medias in this atom **MUST** be document.
    """

    def __init__(self, text: Text | None = None, **kw) -> None:
        super().__init__(**kw)
        self.text = text
        self.builder = MediaGroupBuilder()

    @MsgAtom.reply_markup.getter
    def reply_markup(self):
        return None

    @reply_markup.setter
    def reply_markup(self, value: ReplyMarkup | None):
        assert value is None

    async def __call__(self, bot: Bot, *args, **kwds) -> Sequence[Message]:
        assert self.builder._media
        if self.text:
            self.builder.caption, self.builder.caption_entities = self.text.render()
        return await bot.send_media_group(*args, media=self.builder.build(), **(self.kwds | kwds))

    def append(self, meta: VisualMedia, raw: bytes | None, cls: InputMediaType, **kw):
        """append a media into this atom."""
        assert cls in (InputMediaType.PHOTO, InputMediaType.DOCUMENT, InputMediaType.VIDEO)
        assert len(self.builder._media) < MAX_GROUP_MEDIA

        if raw:
            media = BufferedInputFile(raw, url_basename(meta.raw))
        else:
            media = meta.raw
        self.builder.add(type=cls, media=media, **kw)

    @classmethod
    def pipeline(
        cls,
        txt: Text,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMediaType],
        **kwds,
    ) -> tuple[Self, PIPE_OBJS]:
        """See :meth:`MsgPartial.pipeline`.

        .. note::

            If one media will be sent as a document, and not all of medias in this atom
            is document, this media will be sent as a link in caption, with a reason.
        """
        self = cls(**kwds)
        hint = Text()
        n_pipe = n_media = 0

        while n_media < MAX_GROUP_MEDIA:
            if not (metas and raws and md_types):
                break

            n_pipe += 1
            meta = metas[0]
            ty = md_types[0]

            match ty:
                case InputMediaType.DOCUMENT if self.is_doc is not False:
                    if meta.is_video:
                        note = Text(f"P{n_pipe}: 不支持的视频格式，点击查看", TextLink("原视频", url=meta.raw))
                    else:
                        note = Text(f"P{n_pipe}: 图片过大无法发送/显示，点击查看", TextLink("原图", url=meta.raw))

                    if len(hint) + len(note) <= LIM_MD_TXT - 1:
                        hint += note
                        self.is_doc = True
                    else:
                        break

                case InputMediaType.ANIMATION:
                    ty = InputMediaType.PHOTO
                    note = Text("P{n_pipe}: 不支持动图，点击查看", TextLink("原图", url=meta.raw))
                    if len(hint) + len(note) <= LIM_MD_TXT - 1:
                        hint += note
                    else:
                        break

                case _:
                    if ty != InputMediaType.DOCUMENT and self.is_doc is True:
                        break
                    self.is_doc = False

            self.append(metas.pop(0), raws.pop(0), ty)
            md_types.pop(0)
            n_media += 1

        if n_hint := len(hint):
            rest = LIM_MD_TXT - n_hint - 2
        else:
            rest = LIM_MD_TXT

        self.text = as_list(txt[:rest], hint, sep="\n\n")
        return self, (txt[rest:], metas, raws, md_types)
