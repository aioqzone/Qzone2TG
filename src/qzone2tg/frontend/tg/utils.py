from math import ceil
from pathlib import PurePath
from typing import Callable, Optional, Union
from urllib.parse import urlparse

import telegram
from qzone2tg.utils.decorator import FloodControl
from telegram.bot import Bot

TEXT_LIM = 4096
MEDIA_TEXT_LIM = 1024
MEDIA_GROUP_LIM = 10


class _FloodCtrl:
    def __init__(self, tps: int = 30) -> None:
        self._fc = FloodControl(tps)

    @staticmethod
    def sendMessage(text: str, reply_markup=None, **kw):
        if text: return ceil(len(text) / TEXT_LIM)
        return 0

    @staticmethod
    def sendMedia(text: Optional[str], media: list, reply_markup=None, **kw):
        if not media:
            return ceil(len(text) / TEXT_LIM)
        if len(media) == 1:
            if text is None: return 1
            return 1 + ceil((len(text) - MEDIA_TEXT_LIM) / TEXT_LIM)
        if reply_markup:
            return ceil(len(text) / TEXT_LIM) + len(media)

        return len(media)

    def needfc(self, func: Callable):
        return self._fc(getattr(self, func.__name__, None))(func)


class FixUserBot:
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        times_per_second: int = None,
    ) -> None:
        self.to = chat_id
        self._bot = bot
        self._register_flood_control(times_per_second or 30)

    def _register_flood_control(self, tps: int):
        fc = _FloodCtrl(tps or 30)
        for i in [self.sendMessage, self.sendMedia, self.editMedia]:
            setattr(self, i.__name__, fc.needfc(i))

    def sendMessage(self, text: str, reply_markup=None, *, reply: int = None, **kw):
        assert text
        if len(text) < TEXT_LIM:
            return [
                self._bot.send_message(
                    text=text,
                    chat_id=self.to,
                    reply_markup=reply_markup,
                    reply_to_message_id=reply,
                    **kw
                )
            ]

        i = self.sendMessage(text[:TEXT_LIM], reply_markup, **kw)[0]
        return i + self.sendMessage(text[TEXT_LIM:], reply=i[-1].message_id, **kw)

    @staticmethod
    def getExt(url: str):
        assert isinstance(url, str)
        return PurePath(urlparse(url).path).suffix

    def _send_single(self, media: Union[str, bytes], **kwargs):
        if isinstance(media, bytes):
            return self._bot.send_photo(photo=media, **kwargs)
        if self.getExt(media) == '.mp4':
            return self._bot.send_video(video=media, **kwargs)
        else:
            return self._bot.send_photo(photo=media, **kwargs)

    @classmethod
    def single_media(cls, media: Union[str, bytes], **kwargs):
        if isinstance(media, bytes):
            return telegram.InputMediaPhoto(media=media, **kwargs)
        if cls.getExt(media) == '.mp4':
            return telegram.InputMediaVideo(media=media, **kwargs)
        else:
            return telegram.InputMediaPhoto(media=media, **kwargs)

    def editMedia(self, msg: telegram.Message, media: Union[str, bytes]):
        m_obj = self.single_media(media=media, caption=msg.caption)
        try:
            # TODO: maintain an estimate of read time?
            return msg.edit_media(media=m_obj, reply_markup=msg.reply_markup)
        except telegram.error.TelegramError:
            pass
        try:
            telegram.Bot.edit_message_media
            return msg.edit_media(media=m_obj, reply_markup=msg.reply_markup, timeout=20)
        except telegram.error.TelegramError:
            return msg

    def sendMedia(
        self,
        text: Optional[str],
        media: list[Union[str, bytes]],
        reply_markup=None,
        reply: int = None,
        **kw
    ):
        if len(media) == 1:
            if len(text) <= MEDIA_TEXT_LIM:
                return [
                    self._send_single(
                        media[0],
                        chat_id=self.to,
                        caption=text,
                        reply_markup=reply_markup,
                        reply_to_message_id=reply,
                        **kw
                    )
                ]

            i = self.sendMedia(text[:MEDIA_TEXT_LIM], media, reply_markup, **kw)
            return i + self.sendMessage(text[MEDIA_TEXT_LIM:], reply=i[-1].message_id, **kw)

        if reply_markup:
            i = self.sendMessage(text, reply_markup, **kw)
            return self.sendMedia(None, media, reply=i[-1].message_id, **kw)

        if len(media) > MEDIA_GROUP_LIM:
            i = self.sendMedia(text, media[:MEDIA_GROUP_LIM], **kw)
            return self.sendMedia(None, media[MEDIA_GROUP_LIM:], reply=i[-1].message_id, **kw)

        return self._bot.send_media_group(
            chat_id=self.to,
            media=[self.single_media(media[0], caption=text)] + \
                    [self.single_media(i) for i in media[1:]],
            reply_to_message_id=reply
        )
