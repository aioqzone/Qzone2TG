import asyncio
from functools import partial
import logging
from pathlib import PurePath
from typing import Optional, Type, Union

from aiohttp import ClientSession
from aioqzone_feed.type import VisualMedia
from pydantic import HttpUrl
from telegram import Bot
from telegram import InputMediaAnimation
from telegram import InputMediaPhoto
from telegram import InputMediaVideo
from telegram.error import BadRequest

from qzone3tg.utils.iter import split_by_len

from .queue import RelaxSemaphore

TEXT_LIM = 4096
MEDIA_TEXT_LIM = 1024
MEDIA_GROUP_LIM = 10

InputMedia = Union[InputMediaPhoto, InputMediaVideo, InputMediaAnimation]
ChatId = Union[str, int]
logger = logging.getLogger(__name__)

__all__ = ['LimitedBot']


class SemaBot:
    """Basic limited bot with a semaphore. Cannot handle media/text exceeds the limit."""
    def __init__(self, bot: Bot, freq_limit: int = 30) -> None:
        self.bot = bot
        self.sem = RelaxSemaphore(freq_limit)
        self._loop = asyncio.get_event_loop()

    async def send_message(self, to: ChatId, text: str, **kw):
        assert len(text) < TEXT_LIM
        kwds = dict(chat_id=to, text=text)
        func = partial(self.bot.send_message, **kwds, **kw)
        async with self.sem.num():
            return await self._loop.run_in_executor(None, func)

    async def send_photo(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        assert len(text) < MEDIA_TEXT_LIM
        kwds = dict(
            chat_id=to, caption=text, photo=str(media) if isinstance(media, HttpUrl) else media
        )
        func = partial(self.bot.send_photo, **kwds, **kw)
        async with self.sem.num():
            return await self._loop.run_in_executor(None, func)

    async def send_animation(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        assert len(text) < MEDIA_TEXT_LIM
        kwds = dict(
            chat_id=to,
            caption=text,
            animation=str(media) if isinstance(media, HttpUrl) else media
        )
        func = partial(self.bot.send_animation, **kwds, **kw)
        async with self.sem.num():
            return await self._loop.run_in_executor(None, func)

    async def send_video(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        assert len(text) < MEDIA_TEXT_LIM
        kwds = dict(chat_id=to, caption=text, video=str(media))
        func = partial(self.bot.send_video, **kwds, **kw)
        async with self.sem.num():
            return await self._loop.run_in_executor(None, func)

    async def send_media_group(self, to: ChatId, media: list[InputMedia], **kw):
        assert len(media) < MEDIA_GROUP_LIM
        kwds = dict(chat_id=to, media=media)
        func = partial(self.bot.send_media_group, **kwds, **kw)
        async with self.sem.num(len(media)):
            return await self._loop.run_in_executor(None, func)

    async def edit_media(self, to: ChatId, message_id: int, media: InputMedia):
        kwds = dict(chat_id=to, message_id=message_id, media=media)
        func = partial(self.bot.edit_message_media, **kwds)
        async with self.sem.num():
            return await self._loop.run_in_executor(None, func)


class LimitedBot(SemaBot):
    """Add support for media/text exceeds the limit."""
    async def send_message(self, to: ChatId, text: str, **kw):
        reply: Optional[int] = kw.pop('reply_to_message_id', None)
        markup = kw.pop('reply_markup', None)
        for i in split_by_len(text, TEXT_LIM):
            msg = await super().send_message(
                to, i, **kw, reply_to_message_id=reply, reply_markup=markup
            )
            yield msg
            reply = msg.message_id
            markup = None

    async def send_photo(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        meth = super(
        ).send_animation if isinstance(media, bytes) and self.is_gif(media) else super().send_photo
        yield (msg := await meth(to, text[:MEDIA_TEXT_LIM], media, **kw))
        kw.pop('reply_markup', None)
        async for msg in self.send_message(to, text[MEDIA_TEXT_LIM:], **kw,
                                           reply_to_message_id=msg.message_id):
            yield msg

    async def send_animation(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        yield (msg := await super().send_animation(to, text, media, **kw))
        kw.pop('reply_markup', None)
        async for msg in self.send_message(to, text[MEDIA_TEXT_LIM:], **kw,
                                           reply_to_message_id=msg.message_id):
            yield msg

    async def send_video(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        yield (msg := await super().send_video(to, text[:MEDIA_TEXT_LIM], media, **kw))
        kw.pop('reply_markup', None)
        async for msg in self.send_message(to, text[MEDIA_TEXT_LIM:], **kw,
                                           reply_to_message_id=msg.message_id):
            yield msg

    async def send_media_group(self, to: ChatId, media: list[InputMedia], **kw):
        for i in split_by_len(media, MEDIA_GROUP_LIM):
            for msg in await super().send_media_group(to, i, **kw):
                yield msg

    async def unify_send(self, to: ChatId, text: str, medias: list[VisualMedia] = None, **kw):
        if not medias:
            return self.send_message(to, text, **kw)

        first = medias[0]
        meth = self.send_video if first.is_video else self.send_photo
        if len(medias) == 1:
            return meth(to, text, first.raw, **kw)

        kw.pop('reply_markup', None)
        ipmds = [await self.wrap_media(first, caption=text, **kw)]
        ipmds += [await self.wrap_media(i, **kw) for i in medias[1:]]
        return self.send_media_group(to, ipmds, **kw)

    async def edit_media(self, to: ChatId, message_id: list[int], medias: list[VisualMedia]):
        g = (
            super().edit_media(to, mid, await self.wrap_media(media))
            for mid, media in zip(message_id, medias)
        )
        return await asyncio.gather(*g)

    @staticmethod
    def supported_video(url: HttpUrl):
        return PurePath(url.path).suffix in ['.mp4']

    @staticmethod
    def is_gif(b: bytes):
        return b.startswith((b'47494638', b'GIF89a', b'GIF87a'))

    @classmethod
    async def wrap_media(
        cls,
        media: Union[VisualMedia, bytes],
        media_cls: Type[InputMedia] = None,
        **kwds
    ) -> InputMedia:
        """Wrap a media object with :external:class:`telegram.InputMedia`:.

        :param media: media url, photo or video. If video, mp4 only.
        :param media_cls: media class. Needed when media is bytes, ommitted when media is url.

        :raises ValueError: if media ext not supported
        :return: InputMedia object.

        .. note::
            This method is not async. The async syntax is for allowing subclass
            implementing async logic, e.g. make async request.
        """
        if isinstance(media, bytes):
            assert media_cls
            kwds['media'] = media
        else:
            kwds['media'] = str(media.raw)
            media_cls = media_cls or (InputMediaVideo if media.is_video else InputMediaPhoto)
            if media_cls is InputMediaVideo and not cls.supported_video(media.raw):
                raise ValueError(media.raw)
            if media_cls in (InputMediaVideo, InputMediaAnimation) and media.thumbnail:
                kwds['thumb'] = kwds.get('thumb') or str(media.thumbnail)
        return media_cls(**kwds)


class Fetcher:
    def __init__(self, sess: ClientSession, epsilon=5e-6) -> None:
        self.sess = sess
        self.eps = epsilon
        self.tpa = epsilon

    async def __call__(self, url: HttpUrl) -> Optional[bytes]:
        """Get content w/o streaming. `@noexcept`"""
        async with self.sess.get(url) as r:
            try:
                return await r.content.read()
            except:
                return

    def timeout(self):
        self.tpa *= 2

    def succ(self):
        self.tpa = max(self.eps, self.tpa - self.eps)

    def pred_timeout(self, media: VisualMedia):
        p = media.width * media.height
        if media.is_video: return max(20, self.tpa * p * 4)
        else: return max(5, self.tpa * p)


class FetchBot(LimitedBot):
    """Predict image size and fetch timeout when request; Fetch media on this server if BadRequest."""
    def __init__(
        self,
        sess: ClientSession,
        bot: Bot,
        freq_limit: int = 30,
        send_gif_as_anim: bool = False
    ) -> None:
        super().__init__(bot, freq_limit)
        self.fetcher = Fetcher(sess)
        self.prob_gif = send_gif_as_anim

    def unify_send(
        self, to: ChatId, text: str, medias: list[VisualMedia] = None, fetch: bool = False, **kw
    ):
        """Send text with media.

        :param to: send to
        :param text: text or caption
        :param media: media list, defaults to None
        :param fetch: Fetch url by this server. By default, the url will be fetched on telegram server.
        But some url has irregular standard and will cause a :external:exc:`telegram.error.BadRequest`.
        Under such condition, we shall retry with this flag set, and send bytes to telegram.

        :yield: messages
        """
        kw['fetch'] = fetch
        kw['timeout'] = sum(self.fetcher.pred_timeout(i) for i in medias) if medias else None
        return super().unify_send(to, text, medias, **kw)

    async def wrap_media(
        self,
        media: Union[VisualMedia, bytes],
        media_cls: Type[InputMedia] = None,
        fetch: bool = False,
        **kwds
    ) -> InputMedia:
        """Wrap a media object with :external:class:`telegram.InputMedia`:.

        :param media: media url, photo or video. If video, mp4 only.
        :param media_cls: media class. Needed when media is bytes, ommitted when media is url.

        :raises ValueError: if media ext not supported
        :raises `telegram.error.BadRequest`: if any exception in fetcher
        :return: InputMedia object.
        """
        kwds.pop('timeout', None)
        if isinstance(media, VisualMedia) and (fetch or self.prob_gif and not media.is_video):
            m = await self.fetcher(media.raw)
            if m is None:
                logger.error('%s is not a valid media url', str(media.raw))
                raise BadRequest(str(media.raw))
            if media.is_video:
                media_cls = InputMediaVideo
            else:
                media_cls = InputMediaAnimation if self.is_gif(m) else InputMediaPhoto
            media = m

        return await super().wrap_media(media, media_cls, **kwds)

    def send_message(self, to: ChatId, text: str, fetch: bool = False, **kw):
        return super().send_message(to, text, **kw)

    async def send_photo(
        self, to: ChatId, text: str, media: Union[HttpUrl, bytes], fetch: bool = False, **kw
    ):
        if isinstance(media, HttpUrl) and (self.prob_gif or fetch):
            if (m := await self.fetcher(media)) is None:
                if fetch: raise BadRequest(str(media))
            else: media = m

        async for i in super().send_photo(to, text, media, **kw):
            yield i

    async def send_animation(
        self, to: ChatId, text: str, media: Union[HttpUrl, bytes], fetch: bool = False, **kw
    ):
        if isinstance(media, HttpUrl) and fetch:
            m = await self.fetcher(media)
            if m is None: raise BadRequest(str(media))
            media = m

        async for i in super().send_animation(to, text, media, **kw):
            yield i

    def send_video(
        self, to: ChatId, text: str, media: Union[HttpUrl, bytes], fetch: bool = False, **kw
    ):
        return super().send_video(to, text, media, **kw)

    def send_media_group(self, to: ChatId, media: list[InputMedia], fetch: bool = False, **kw):
        return super().send_media_group(to, media, **kw)

    def edit_media(
        self, to: ChatId, message_id: list[int], medias: list[VisualMedia], fetch: bool = False
    ):
        return super().edit_media(to, message_id, medias)
