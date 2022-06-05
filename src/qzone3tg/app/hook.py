"""Defines all hooks used in Qzone3TG and implements some default hook.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Type

from aioqzone.interface.hook import LoginEvent, LoginMethod, QREvent, UPEvent
from aioqzone_feed.interface.hook import FeedContent, FeedEvent
from telegram import InlineKeyboardMarkup, InputMediaPhoto, Message

from qzone3tg.bot import BotProtocol, ChatId
from qzone3tg.bot.queue import EditableQueue

log = logging.getLogger(__name__)


class Sender(ABC):
    @property
    @abstractmethod
    def admin(self) -> ChatId:
        pass

    @property
    @abstractmethod
    def bot(self) -> BotProtocol:
        pass

    async def notify(self, text: str, **kw):
        """Shortcut to `.bot.send_message` with `to` set as `.admin`."""
        await self.bot.send_message(self.admin, text, **kw)


class DefaultQrHook(QREvent, Sender):
    def __init__(self) -> None:
        super().__init__()
        self.qr_msg: Message | None = None
        self.qr_times: int = 0
        """qr sent counter"""
        self.qr_renew = False
        """qr renew status flag"""

    async def LoginFailed(self, meth, msg: Optional[str] = None):
        pmsg = f": {msg}" if msg else ""
        await super().LoginFailed(meth, msg)
        self.cleanup()
        await self.notify("二维码登录失败" + pmsg)

    async def LoginSuccess(self, meth):
        await super().LoginSuccess(meth)
        self.cleanup()
        await self.notify("登录成功")

    def qr_markup(self) -> InlineKeyboardMarkup | None:
        return

    async def QrFetched(self, png: bytes, renew: bool = False):
        if self.qr_msg is None:
            self.qr_msg = await self.bot.send_photo(
                self.admin,
                png,
                "扫码登陆:",
                disable_notification=False,
                reply_markup=self.qr_markup(),
            )
        else:
            text = "二维码已刷新:" if self.qr_renew else f"二维码已过期, 请重新扫描[{self.qr_times}]"
            msg = await self.bot.edit_message_media(
                self.admin,
                self.qr_msg.message_id,
                InputMediaPhoto(png, text),
            )
            if isinstance(msg, Message):
                self.qr_msg = msg
        self.qr_times += 1

    def cleanup(self):
        self.qr_times = 0
        if self.qr_msg:
            self.qr_msg.delete()
            self.qr_msg = None


class DefaultUpHook(UPEvent, Sender):
    async def LoginFailed(self, meth, msg: Optional[str] = None):
        pmsg = f": {msg}" if msg else ""
        await super().LoginFailed(meth, msg)
        await self.notify("密码登陆失败" + pmsg)

    async def LoginSuccess(self, meth):
        await self.notify("登录成功")
        return await super().LoginSuccess(meth)


class DefaultLoginHook(DefaultQrHook, DefaultUpHook):
    def __init__(self, admin: ChatId, bot: BotProtocol) -> None:
        QREvent.__init__(self)
        self._admin = admin
        self._bot = bot

    # fmt: off
    @property
    def admin(self): return self._admin
    @property
    def bot(self): return self._bot
    # fmt: on

    @classmethod
    def _get_base(cls, meth: LoginMethod) -> Type[LoginEvent]:
        return {LoginMethod.up: DefaultUpHook, LoginMethod.qr: DefaultQrHook}[meth]

    async def LoginFailed(self, meth, msg: str | None = None):
        cls = self._get_base(meth)
        await cls.LoginFailed(self, meth, msg)

    async def LoginSuccess(self, meth):
        cls = self._get_base(meth)
        await cls.LoginSuccess(self, meth)


class DefaultFeedHook(FeedEvent):
    def __init__(self, queue: EditableQueue, block: list[int]) -> None:
        super().__init__()
        self.queue = queue
        self.block = set(block)
        self.new_batch = self.queue.new_batch

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        log.debug(f"bid={bid}: {feed}")
        if feed.uin in self.block:
            log.info(f"Block hit: {feed.uin}")
            return await self.FeedDropped(bid, feed)
        await self.queue.add(bid, feed)

    async def FeedDropped(self, bid: int, feed):
        log.debug(f"batch {bid}: one feed dropped")
        self.queue.skip_num += 1

    async def FeedMediaUpdate(self, bid: int, feed: FeedContent):
        log.debug(f"feed update received: media={feed.media}")
        await self.queue.edit(bid, feed)

    async def HeartbeatFailed(self, exc: Optional[BaseException] = None):
        log.debug(f"notify: heartbeat failed: {exc}")

    async def HeartbeatRefresh(self, num: int):
        log.info(f"Heartbeat triggers a refresh: count={num}")
