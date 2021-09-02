from math import ceil
import telegram
from telegram.bot import Bot

from utils.decorator import FloodControl, decoratorWargs


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

    @decoratorWargs(_fc, lambda s, t, *a, **kw: ceil(len(t) / 4096))
    def sendMessage(self, text: str, reply_markup=None, *args, **kwargs):
        assert text
        if len(text) < 4096:
            return [
                self._bot.send_message(
                    text=text,
                    chat_id=self.to,
                    parse_mode=self.parse_mode,
                    reply_markup=reply_markup
                )
            ]
        else:
            return self.sendMessage(text[:4096], reply_markup, *args, **kwargs) + \
                   self.sendMessage(text[4096:], None, *args, **kwargs)

    @decoratorWargs(
        _fc,
        lambda s, m, i, b=None, *a, **kw: ceil(len(m) / 4096)
        if not i else 1 + (ceil((len(m) - 1024) / 4096) if m else 0)
        if len(i) == 1 else ceil(len(m) / 4096) + len(i) if b else len(i)
    )
    def sendImage(self, text: str, img: list, reply_markup=None, *args, **kwargs):
        if len(img) == 1:
            if len(text) < 1024:
                return [
                    self._bot.send_photo(
                        chat_id=self.to,
                        photo=img[0],
                        caption=text,
                        parse_mode=self.parse_mode,
                        reply_markup=reply_markup
                    )
                ]
            else:
                return self.sendImage(text[:1024], img, reply_markup, *args, **kwargs) + \
                       self.sendMessage(text[1024:], None, *args, **kwargs)
        elif reply_markup:
            return self.sendMessage(text, reply_markup, *args, **kwargs) + \
                   self.sendImage(None, img, *args, **kwargs)
        elif len(img) > 10:
            return self.sendImage(text, img[:10], *args, **kwargs) + \
                   self.sendImage(None, img[10:], *args, **kwargs)
        else:
            return self._bot.send_media_group(
                chat_id=self.to,
                media=[telegram.InputMediaPhoto(media=img[0], caption=text, parse_mode=self.parse_mode)] + \
                      [telegram.InputMediaPhoto(i) for i in img[1:]]
            )
