"""This module split a feed into multiple atomic message."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Final, Sequence

from aiogram import Bot
from aiogram.enums.input_media_type import InputMediaType
from aiogram.types.input_file import BufferedInputFile
from aiogram.types.input_media_animation import InputMediaAnimation as Anim
from aiogram.types.input_media_document import InputMediaDocument as Doc
from aiogram.types.input_media_photo import InputMediaPhoto as Pic
from aiogram.types.input_media_video import InputMediaVideo as Video
from aiogram.types.message import Message
from aiogram.utils.media_group import MediaGroupBuilder
from aioqzone_feed.type import VisualMedia

if TYPE_CHECKING:
    from typing_extensions import Self

    from . import ReplyMarkup, SupportMedia

    PIPE_OBJS = tuple[str, list[VisualMedia], list[bytes | None], list[InputMediaType]]

MAX_GROUP_MEDIA: Final[int] = 10
MAX_TEXT_LENGTH: Final[int] = 4096
CAPTION_LENGTH: Final[int] = 1024
LIM_TXT: Final[int] = MAX_TEXT_LENGTH - 1
LIM_MD_TXT: Final[int] = CAPTION_LENGTH - 1

log = logging.getLogger(__name__)


def href(txt: str, url: str):
    url = url.replace("'", "\\'")
    return f"<a href='{url}'>{txt}</a>"


def url_basename(url: str):
    return url[url.rfind("/") + 1 :]


class MsgPartial(ABC):
    """Message partial is the atomic unit to send/retry in sending progress.
    One feed can be seperated into more than one partials. One partial corresponds
    to one function call in aspect of behavior."""

    __slots__ = ("kwds", "meth", "text")
    meth: ClassVar[str]
    text: str | None

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
        """Partial timeout. Since one partial is the atomic unit to send/retry in sending progress,
        every partial has its own timeout.
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


class TextPartial(MsgPartial):
    """Text partial represents a pure text message.
    Calling this will trigger :meth:`Bot.send_message`.
    """

    meth = "message"

    def __init__(self, text: str, **kw) -> None:
        super().__init__(**kw)
        self.text = text

    async def __call__(self, bot: Bot, *args, **kwds) -> Message:
        assert self.text
        return await bot.send_message(*args, text=self.text, **(self.kwds | kwds))

    @classmethod
    def pipeline(
        cls,
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMediaType],
        **kwds,
    ) -> tuple[Self, PIPE_OBJS]:
        return cls(txt[:LIM_TXT], **kwds), (txt[LIM_TXT:], metas, raws, md_types)


class MediaPartial(MsgPartial):
    """Media partial represents a message with **ONE** media. Each MediaPartial should have
    a :obj:`.meth` field which indicates what kind of media it contains. The meth is also used
    when MediaPartial is called. Thus "send_{meth}" must be a callable in :class:`Bot`.
    """

    __slots__ = ("meta", "_raw", "__md_cls__")
    __md_cls__: ClassVar[type[SupportMedia]]
    meth: ClassVar[InputMediaType]

    def __init__(
        self,
        media: VisualMedia,
        raw: bytes | None,
        text: str | None = None,
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
        return await f(*args, caption=self.text, **(self.kwds | kwds))

    @classmethod
    def pipeline(
        cls,
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMediaType],
        **kwds,
    ) -> tuple["MediaPartial", PIPE_OBJS]:
        cls = InputMedia2Partial[md_types[0]]

        return (
            cls(metas[0], raws[0], txt[:LIM_MD_TXT], **kwds),
            (txt[LIM_MD_TXT:], metas[1:], raws[1:], md_types[1:]),
        )


class AnimPartial(MediaPartial):
    meth = InputMediaType.ANIMATION
    __md_cls__ = Anim

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


class DocPartial(MediaPartial):
    meth = InputMediaType.DOCUMENT
    __md_cls__ = Doc


class PicPartial(MediaPartial):
    meth = InputMediaType.PHOTO
    __md_cls__ = Pic


class VideoPartial(MediaPartial):
    meth = InputMediaType.VIDEO
    __md_cls__ = Video

    @property
    def thumb(self):
        return str(self.meta.thumbnail)


InputMedia2Partial = {
    InputMediaType.ANIMATION: AnimPartial,
    InputMediaType.DOCUMENT: DocPartial,
    InputMediaType.PHOTO: PicPartial,
    InputMediaType.VIDEO: VideoPartial,
}


class MediaGroupPartial(MsgPartial):
    """MediaGroupPartial represents a group of medias in one message. Calling this will trigger
    :meth:`Bot.send_media_group`.
    """

    meth = "media_group"
    is_doc: bool | None = None
    """If the first media is Document.

        .. note:: If True, then any other medias in this partial **MUST** be document.
    """

    def __init__(self, text: str | None = None, **kw) -> None:
        super().__init__(**kw)
        self.text = text
        self.builder = MediaGroupBuilder()

    @MsgPartial.reply_markup.getter
    def reply_markup(self):
        return None

    @reply_markup.setter
    def reply_markup(self, value: ReplyMarkup | None):
        assert value is None

    async def __call__(self, bot: Bot, *args, **kwds) -> Sequence[Message]:
        assert self.builder._media
        self.builder.caption = self.text
        return await bot.send_media_group(*args, media=self.builder.build(), **(self.kwds | kwds))

    def append(self, meta: VisualMedia, raw: bytes | None, cls: InputMediaType, **kw):
        """append a media into this partial."""
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
        txt: str,
        metas: list[VisualMedia],
        raws: list[bytes | None],
        md_types: list[InputMediaType],
        **kwds,
    ) -> tuple[Self, PIPE_OBJS]:
        """See :meth:`MsgPartial.pipeline`.

        .. note::

            If one media will be sent as a document, and not all of medias in this partial
            is document, this media will be sent as a link in caption, with a reason.
        """
        self = cls(**kwds)
        hint = ""
        n_pipe = n_media = 0

        while n_media < MAX_GROUP_MEDIA:
            if not (metas and raws and md_types):
                break

            n_pipe += 1
            meta = metas[0]
            ty = md_types[0]

            if ty == InputMediaType.DOCUMENT and self.builder and not self.is_doc:
                if meta.is_video:
                    note = f"\nP{n_pipe}: 不支持的视频格式，点击查看{href('原视频', meta.raw)}"
                else:
                    note = f"\nP{n_pipe}: 图片过大无法发送/显示，点击查看{href('原图', meta.raw)}"

                if len(hint) + len(note) <= LIM_MD_TXT - 1:
                    hint += note
                    metas.pop(0)
                    raws.pop(0)
                    md_types.pop(0)
                    continue
                else:
                    break
            if self.builder and self.is_doc and not ty == InputMediaType.DOCUMENT:
                break

            if ty == InputMediaType.ANIMATION:
                ty = InputMediaType.PHOTO
                hint += f"\nP{n_pipe}: 不支持动图，点击查看{href('原图', meta.raw)}"

            self.append(metas.pop(0), raws.pop(0), ty)
            md_types.pop(0)
            n_media += 1

        if hint:
            hint = "\n" + hint
        rest = LIM_MD_TXT - len(hint)

        self.text = txt[:rest] + hint
        return self, (txt[rest:], metas, raws, md_types)
