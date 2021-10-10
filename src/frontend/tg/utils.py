from math import ceil
from pathlib import PurePath
from typing import Callable, Optional
from urllib.parse import urlparse

import telegram
from telegram.bot import Bot

from utils.decorator import FloodControl

TEXT_LIM = 4096
MEDIA_TEXT_LIM = 1024
MEDIA_GROUP_LIM = 10


class _FCHelper:
    _fc = FloodControl(30)

    @staticmethod
    def sendMessage(self, text: str, reply_markup=None, **kw):
        if text: return ceil(len(text) / TEXT_LIM)
        return 0

    @staticmethod
    def sendMedia(self, text: Optional[str], media: list, reply_markup=None, **kw):
        if not media:
            return ceil(len(text) / TEXT_LIM)
        if len(media) == 1:
            if text is None: return 1
            return 1 + ceil((len(text) - MEDIA_TEXT_LIM) / TEXT_LIM)
        if reply_markup:
            return ceil(len(text) / TEXT_LIM) + len(media)

        return len(media)

    @classmethod
    def needfc(cls, func: Callable):
        return cls._fc(getattr(cls, func.__name__))(func)


class FixUserBot:
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        parse_mode: telegram.ParseMode = None,
        times_per_second: int = None,
        disable_notification: bool = False
    ) -> None:
        self.to = chat_id
        self._bot = bot
        self.parse_mode = parse_mode
        _FCHelper._fc.tps = times_per_second or 30
        self.dnn = disable_notification

    @_FCHelper.needfc
    def sendMessage(self, text: str, reply_markup=None, *, reply: int = None, **kw):
        assert text
        if len(text) < TEXT_LIM:
            return [
                self._bot.send_message(
                    text=text,
                    chat_id=self.to,
                    parse_mode=self.parse_mode,
                    reply_markup=reply_markup,
                    reply_to_message_id=reply,
                    disable_notification=self.dnn,
                    **kw
                )
            ]

        i = self.sendMessage(text[:TEXT_LIM], reply_markup, **kw)[0]
        return i + self.sendMessage(text[TEXT_LIM:], reply=i[-1].message_id, **kw)

    @staticmethod
    def getExt(url):
        return PurePath(urlparse(url).path).suffix

    def _send_single(self, media: str, **kwargs):
        if self.getExt(media) == '.mp4':
            return self._bot.send_video(video=media, **kwargs)
        else:
            return self._bot.send_photo(photo=media, **kwargs)

    @classmethod
    def _single_media(cls, media: str, **kwargs):
        if cls.getExt(media) == '.mp4':
            return telegram.InputMediaVideo(media=media, **kwargs)
        else:
            return telegram.InputMediaPhoto(media=media, **kwargs)

    @_FCHelper.needfc
    def sendMedia(
        self,
        text: Optional[str],
        media: list,
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
                        parse_mode=self.parse_mode,
                        reply_markup=reply_markup,
                        reply_to_message_id=reply,
                        disable_notification=self.dnn,
                        **kw
                    )
                ]

            i = self.sendMedia(text[:MEDIA_TEXT_LIM], media, reply_markup, **kw)
            return i + self.sendMessage(
                text[MEDIA_TEXT_LIM:], reply=i[-1].message_id, **kw
            )

        if reply_markup:
            i = self.sendMessage(text, reply_markup, **kw)
            return self.sendMedia(None, media, reply=i[-1].message_id, **kw)

        if len(media) > MEDIA_GROUP_LIM:
            i = self.sendMedia(text, media[:MEDIA_GROUP_LIM], **kw)
            return self.sendMedia(
                None, media[MEDIA_GROUP_LIM:], reply=i[-1].message_id, **kw
            )

        return self._bot.send_media_group(
            chat_id=self.to,
            media=[self._single_media(media[0], caption=text, parse_mode=self.parse_mode)] + \
                    [self._single_media(i) for i in media[1:]],
            reply_to_message_id=reply,
            disable_notification=True
        )
