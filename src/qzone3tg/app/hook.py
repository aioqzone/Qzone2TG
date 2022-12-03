"""Defines all hooks used in Qzone3TG and implements some default hook.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import telegram
from aioqzone.event.login import QREvent, UPEvent
from aioqzone_feed.interface.hook import FeedContent, FeedEvent
from telegram import InlineKeyboardMarkup, InputMediaPhoto, Message
from telegram.error import BadRequest

from qzone3tg.bot import BotProtocol, ChatId
from qzone3tg.bot.queue import EditableQueue

log = logging.getLogger(__name__)


@dataclass
class Sender:
    admin: ChatId
    bot: BotProtocol

    async def notify(self, text: str, **kw):
        """Shortcut to `.bot.send_message` with `to` set as `.admin`."""
        return await self.bot.send_message(self.admin, text, **kw)


class DefaultQrHook(QREvent, Sender):
    def __init__(self, admin: ChatId, bot: BotProtocol) -> None:
        super().__init__(admin, bot)
        self.qr_msg: Message | None = None
        """qr sent counter"""
        self.qr_renew = False
        """qr renew status flag"""
        self._refresh = asyncio.Event()
        self._cancel = asyncio.Event()

    async def LoginFailed(self, meth, msg: Optional[str] = None):
        pmsg = f": {msg}" if msg else ""
        await super().LoginFailed(meth, msg)
        await self.cleanup()
        await self.notify("二维码登录失败" + pmsg)

    async def LoginSuccess(self, meth):
        await super().LoginSuccess(meth)
        await self.cleanup()
        await self.notify("登录成功")

    def qr_markup(self) -> InlineKeyboardMarkup | None:
        return

    async def QrFetched(self, png: bytes, times: int):
        if self.qr_msg is None:
            self.qr_msg = await self.bot.send_photo(
                self.admin,
                png,
                "扫码登陆:",
                disable_notification=False,
                reply_markup=self.qr_markup(),
            )
        else:
            text = "二维码已刷新:" if self.qr_renew else f"二维码已过期, 请重新扫描[{times}]"
            msg = await self.bot.edit_message_media(
                self.admin,
                self.qr_msg.message_id,
                InputMediaPhoto(png, text),
                reply_markup=self.qr_markup(),
            )
            if isinstance(msg, Message):
                self.qr_msg = msg

    async def cleanup(self):
        if self.qr_msg:
            try:
                await self.qr_msg.delete()
            except BadRequest as e:
                log.warning(e)
            finally:
                self.qr_msg = None

    @property
    def refresh_flag(self) -> asyncio.Event:
        return self._refresh

    @property
    def cancel_flag(self) -> asyncio.Event:
        return self._cancel


class DefaultUpHook(UPEvent, Sender):
    def __init__(self, admin: ChatId, bot: BotProtocol, vcode_timeout: float = 10) -> None:
        super().__init__(admin, bot)
        self.vtimeout = vcode_timeout

    async def LoginFailed(self, meth, msg: Optional[str] = None):
        pmsg = f": {msg}" if msg else ""
        await super().LoginFailed(meth, msg)
        await self.notify("密码登录失败" + pmsg)

    async def LoginSuccess(self, meth):
        await self.notify("登录成功", disable_notification=True)
        await super().LoginSuccess(meth)

    async def GetSmsCode(self, phone: str, nickname: str) -> Optional[str]:
        m = await self.notify(
            f"将要登录的是{nickname}，请输入密保手机({phone})上收到的验证码:",
            disable_notification=False,
            reply_markup=telegram.ForceReply(input_field_placeholder="012345"),
        )
        code = await self.force_reply_answer(m)
        if code is None:
            await self.notify("超时未回复")
            await m.edit_reply_markup(reply_markup=None)
            return

        if len(code) != 6:
            await self.notify("应回复六位数字验证码")
            await m.edit_reply_markup(reply_markup=None)
            return
        return code

    async def force_reply_answer(self, msg: Message) -> str | None:
        """A hook cannot get answer from the user. This should be done by handler in app.
        So this method should be implemented in app level.

        :param msg: The force reply message to wait for the reply from user.
        :param timeout: wait timeout
        :return: None if timeout, else the reply string.
        """
        return


class DefaultFeedHook(FeedEvent):
    def __init__(self, queue: EditableQueue, block: list[int]) -> None:
        super().__init__()
        self.queue = queue
        self.block = set(block)
        self.new_batch = self.queue.new_batch

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        log.debug(f"bid={bid}: {feed}")
        if feed.uin in self.block:
            log.info(f"Blocklist hit: {feed.uin}({feed.nickname})")
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
