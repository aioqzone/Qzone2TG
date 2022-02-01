"""Inherits all hooks from aioqzone and implements hook behavior."""

from collections import defaultdict
from typing import Optional, Union

from aioqzone.interface.hook import Emittable
from aioqzone.interface.hook import LoginEvent
from aioqzone.interface.hook import QREvent
from aioqzone_feed.interface.hook import FeedContent
from aioqzone_feed.interface.hook import FeedEvent
from telegram import Bot
from telegram import Message

from ..utils.iter import anext_
from .limitbot import LimitedBot
from .queue import ForwardEvent
from .queue import MsgScheduler


class ForwardHook(LoginEvent, QREvent, FeedEvent, ForwardEvent, Emittable):
    def __init__(self, bot: Bot, admin: Union[str, int]) -> None:
        super().__init__()
        self.bot = LimitedBot(bot)
        self.admin = admin
        self.qr_times: int = 0
        self.qr_msg: Optional[Message] = None
        self.lg_msg: Optional[Message] = None
        self.msg_scd: Optional[MsgScheduler] = None
        self.forward_map = defaultdict(lambda: admin)

    async def LoginFailed(self, msg: str = None):
        async for i in self.bot.send_message(self.admin, text=msg or '登录失败'):
            pass

    async def LoginSuccess(self):
        self.lg_msg = await anext_(self.bot.send_message(self.admin, '登录成功'))

    async def QrFetched(self, png: bytes, renew: bool = False):
        text = '二维码已刷新:' if renew else f'二维码已过期, 请重新扫描[{self.qr_times}]' if self.qr_times else '扫码登陆:'
        self.qr_msg = await anext_(
            self.bot.send_photo(self.admin, text, png, disable_notification=False)
        )
        self.qr_times += 1

    async def QrFailed(self, msg: str = None):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None
        await anext_(self.bot.send_message(self.admin, '二维码登录失败' + (f': {msg}' if msg else '')))

    async def QrSucceess(self):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        assert self.msg_scd
        await self.msg_scd.add(bid, feed)

    async def FeedMediaUpdate(self, feed: FeedContent):
        return await super().FeedMediaUpdate(feed)

    def new_batch(self, val: int = 0, max_retry: int = 2):
        self.msg_scd = MsgScheduler(val, max_retry)
        self.msg_scd.register_hook(self)

    async def SendNow(self, feed: FeedContent):
        media = [i.raw for i in feed.media] if feed.media else []
        agen = self.bot.unify_send(self.forward_map[feed.uin], feed.content, media)
        async for i in agen:
            pass    # TODO: storage

    async def FeedDroped(self, feed: FeedContent, *exc):
        pass
