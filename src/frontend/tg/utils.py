from math import ceil
from pathlib import PurePath
from urllib.parse import urlparse

import telegram
from telegram.bot import Bot

from utils.decorator import FloodControl


class FixUserBot:
    _fc = FloodControl(30)

    def __init__(
        self, bot: Bot, chat_id: int, parse_mode: telegram.ParseMode = None
    ) -> None:
        self.to = chat_id
        self._bot = bot
        self.parse_mode = parse_mode

    @classmethod
    def register_flood_control(cls, *args, **kwargs):
        cls._fc = FloodControl(*args, **kwargs)

    @_fc(lambda s, t=None, b=None, **kw: ceil(len(t) / 4096) if t else 0)
    def sendMessage(self, text: str, reply_markup=None, **kwargs):
        assert text
        if len(text) < 4096:
            return [
                self._bot.send_message(
                    text=text,
                    chat_id=self.to,
                    parse_mode=self.parse_mode,
                    reply_markup=reply_markup,
                    **kwargs
                )
            ]
        else:
            return self.sendMessage(text[:4096], reply_markup, **kwargs) + \
                   self.sendMessage(text[4096:], None, **kwargs)

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

    @_fc(
        lambda s, m, i, b=None, *a, **kw: ceil(len(m) / 4096)
        if not i else 1 + (ceil((len(m) - 1024) / 4096) if m else 0)
        if len(i) == 1 else ceil(len(m) / 4096) + len(i) if b else len(i)
    )
    def sendMedia(self, text: str, media: list, reply_markup=None, **kwargs):
        if len(media) == 1:
            if len(text) < 1024:
                return [
                    self._send_single(
                        media[0],
                        chat_id=self.to,
                        caption=text,
                        parse_mode=self.parse_mode,
                        reply_markup=reply_markup,
                        **kwargs
                    )
                ]
            else:
                return self.sendMedia(text[:1024], media, reply_markup, **kwargs) + \
                       self.sendMessage(text[1024:], **kwargs)
        elif reply_markup:
            return self.sendMessage(text, reply_markup, **kwargs) + \
                   self.sendMedia(None, media, **kwargs)
        elif len(media) > 10:
            return self.sendMedia(text, media[:10], **kwargs) + \
                   self.sendMedia(None, media[10:], **kwargs)
        else:
            return self._bot.send_media_group(
                chat_id=self.to,
                media=[self._single_media(media[0], caption=text, parse_mode=self.parse_mode)] + \
                      [self._single_media(i) for i in media[1:]],
                disable_notification=True
            )
