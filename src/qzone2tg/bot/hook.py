"""Inherits all hooks from aioqzone and implements hook behavior."""

from collections import defaultdict
from functools import partial
from functools import wraps
from pathlib import PurePath
from typing import Optional, Union

from aioqzone.interface.hook import LoginEvent
from aioqzone.interface.hook import QREvent
from aioqzone_feed.interface.hook import FeedContent
from aioqzone_feed.interface.hook import FeedEvent
from pydantic import HttpUrl
from telegram import Bot
from telegram import InputMediaPhoto
from telegram import InputMediaVideo
from telegram import Message
from telegram import TelegramError
from telegram.ext import Dispatcher

from .queue import RelaxSemaphore

TEXT_LIM = 4096
MEDIA_TEXT_LIM = 1024
MEDIA_GROUP_LIM = 10


class BotHelper:
    def __init__(self, bot: Bot, freq_limit: int = 30) -> None:
        self.bot = bot
        self.sem = RelaxSemaphore(freq_limit)

    async def send_message(self, to: Union[int, str], text: str, **kw):
        assert len(text) < TEXT_LIM
        kwds = dict(chat_id=to, text=text)
        async with self.sem.num():
            return self.bot.send_message(**kwds, **kw)

    async def send_photo(self, to: Union[int, str], text: str, media: Union[HttpUrl, bytes], **kw):
        assert len(text) < MEDIA_TEXT_LIM
        kwds = dict(
            chat_id=to, caption=text, photo=str(media) if isinstance(media, HttpUrl) else media
        )
        async with self.sem.num():
            return self.bot.send_photo(**kwds, **kw)

    async def send_video(self, to: Union[int, str], text: str, media: str, **kw):
        assert len(text) < TEXT_LIM
        kwds = dict(chat_id=to, caption=text, video=media)
        async with self.sem.num():
            return self.bot.send_video(**kwds, **kw)

    async def send_media_group(self, to: Union[int, str], media: list, **kw):
        assert len(media) < MEDIA_GROUP_LIM
        kwds = dict(chat_id=to, media=media)
        async with self.sem.num(len(media)):
            return self.bot.send_media_group(**kwds, **kw)


class UnifiedHook(LoginEvent, QREvent, FeedEvent):
    def __init__(self, bot: Bot, admin: Union[str, int]) -> None:
        super().__init__()
        self.bot = BotHelper(bot)
        self.admin = admin
        self.qr_times: int = 0
        self.qr_msg: Optional[Message] = None
        self.lg_msg: Optional[Message] = None

    async def LoginFailed(self, msg: str = None):
        await self.bot.send_message(self.admin, text=msg or '登录失败')

    async def LoginSuccess(self):
        self.lg_msg = await self.bot.send_message(self.admin, '登录成功')

    async def QrFetched(self, png: bytes, renew: bool = False):
        text = '二维码已刷新:' if renew else f'二维码已过期, 请重新扫描[{self.qr_times}]' if self.qr_times else '扫码登陆:'
        self.qr_msg = await self.bot.send_photo(self.admin, text, png, disable_notification=False)
        self.qr_times += 1

    async def QrFailed(self, msg: str = None):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None
        await self.bot.send_message(self.admin, '二维码登录失败' + (f': {msg}' if msg else ''))

    async def QrSucceess(self):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        return await super().FeedProcEnd(bid, feed)

    async def FeedMediaUpdate(self, feed: FeedContent):
        return await super().FeedMediaUpdate(feed)
