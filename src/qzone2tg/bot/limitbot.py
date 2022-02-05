import asyncio
from pathlib import PurePath
from typing import Optional, Union

from pydantic import HttpUrl
from telegram import Bot
from telegram import InputMediaPhoto
from telegram import InputMediaVideo

from ..utils.iter import anext_
from ..utils.iter import split_by_len
from .queue import RelaxSemaphore

TEXT_LIM = 4096
MEDIA_TEXT_LIM = 1024
MEDIA_GROUP_LIM = 10

InputMedia = Union[InputMediaPhoto, InputMediaVideo]
ChatId = Union[str, int]

__all__ = ['LimitedBot']

class SemaBot:
    def __init__(self, bot: Bot, freq_limit: int = 30) -> None:
        self.bot = bot
        self.sem = RelaxSemaphore(freq_limit)

    async def send_message(self, to: ChatId, text: str, **kw):
        assert len(text) < TEXT_LIM
        kwds = dict(chat_id=to, text=text)
        async with self.sem.num():
            return self.bot.send_message(**kwds, **kw)

    async def send_photo(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        assert len(text) < MEDIA_TEXT_LIM
        kwds = dict(
            chat_id=to, caption=text, photo=str(media) if isinstance(media, HttpUrl) else media
        )
        async with self.sem.num():
            return self.bot.send_photo(**kwds, **kw)

    async def send_video(self, to: ChatId, text: str, media: HttpUrl, **kw):
        assert len(text) < MEDIA_TEXT_LIM
        kwds = dict(chat_id=to, caption=text, video=str(media))
        async with self.sem.num():
            return self.bot.send_video(**kwds, **kw)

    async def send_media_group(self, to: ChatId, media: list[InputMedia], **kw):
        assert len(media) < MEDIA_GROUP_LIM
        kwds = dict(chat_id=to, media=media)
        async with self.sem.num(len(media)):
            return self.bot.send_media_group(**kwds, **kw)

    async def edit_media(self, to: ChatId, message_id: int, media: InputMedia):
        async with self.sem.num():
            return self.bot.edit_message_media(chat_id=to, message_id=message_id, media=media)


class LimitedBot(SemaBot):
    async def send_message(self, to: ChatId, text: str, **kw):
        reply: Optional[int] = kw.pop('reply_to_message_id', None)
        markup = kw.pop('reply_markup', None)
        for i in split_by_len(text, TEXT_LIM):
            msg = await super().send_message(to, i, **kw, reply_to_message_id=reply, reply_markup=markup)
            yield msg
            reply = msg.message_id
            markup = None

    async def send_photo(self, to: ChatId, text: str, media: Union[HttpUrl, bytes], **kw):
        yield msg := await super().send_photo(to, text[:MEDIA_TEXT_LIM], media, **kw)
        kw.pop('reply_markup', None)
        async for msg in self.send_message(to, text[MEDIA_TEXT_LIM:], **kw, reply_to_message_id=msg.message_id):
            yield msg

    async def send_video(self, to: ChatId, text: str, media: HttpUrl, **kw):
        yield msg := await super().send_video(to, text[:MEDIA_TEXT_LIM], media, **kw)
        kw.pop('reply_markup', None)
        async for msg in self.send_message(to, text[MEDIA_TEXT_LIM:], **kw, reply_to_message_id=msg.message_id):
            yield msg

    async def send_media_group(self, to: ChatId, media: list[InputMedia], **kw):
        for _ in split_by_len(media, MEDIA_GROUP_LIM):
            for msg in await super().send_media_group(to, media, **kw):
                yield msg

    async def unify_send(self, to: ChatId, text: str, media: list[HttpUrl], **kw):
        if not media:
            async for msg in self.send_message(to, text, **kw): yield msg

        url = media[0]
        meth = self.send_video if self.supported_video(url) else self.send_photo
        if len(media) == 1:
            yield await anext_(meth(to, text, url, **kw))

        reply: Optional[int] = None
        if (markup := kw.pop('reply_markup', None)):
            agen = meth(to, text, url, **kw, reply_markup=markup)
            yield msg := await anext_(agen)
            reply = msg.message_id
            medias = []
        else:
            medias = [self.wrap_media(url, caption=text, **kw)]
        medias += [self.wrap_media(i, caption=text, **kw) for i in media[1:]]
        async for msg in self.send_media_group(to, medias, **kw, reply_to_message_id=reply):  # type: ignore
            yield msg

    def edit_media(self, to: ChatId, message_id: list[int], media: list[HttpUrl]):
        g = (super().edit_media(to, mid, self.wrap_media(url)) for mid, url in zip(message_id, media))
        return asyncio.gather(*g)

    @staticmethod
    def supported_video(url: HttpUrl):
        return PurePath(url.path).suffix in ['.mp4']

    @classmethod
    def wrap_media(cls, media: HttpUrl, **kwargs):
        if cls.supported_video(media):
            return InputMediaVideo(media=str(media), **kwargs)
        return InputMediaPhoto(media=str(media), **kwargs)
