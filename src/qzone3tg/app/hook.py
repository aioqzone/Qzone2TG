"""Defines all hooks used in Qzone3TG and implements some default hook.
"""

import logging

from aioqzone.interface.hook import QREvent
from aioqzone_feed.interface.hook import FeedContent
from aioqzone_feed.interface.hook import FeedEvent
from telegram import InlineKeyboardMarkup
from telegram import Message

from qzone3tg.bot import BotProtocol
from qzone3tg.bot import ChatId
from qzone3tg.bot.queue import EditableQueue

logger = logging.getLogger(__name__)


class DefaultQrHook(QREvent):
    def __init__(self, admin: ChatId, bot: BotProtocol) -> None:
        QREvent.__init__(self)
        self.admin = admin
        self.bot = bot
        self.qr_msg: Message | None = None
        self.lg_msg: Message | None = None
        self.qr_times: int = 0
        """qr sent times"""

    async def LoginFailed(self, msg: str | None = None):
        pass

    async def LoginSuccess(self):
        self.lg_msg = await self.bot.send_message(self.admin, "登录成功")

    def qr_markup(self) -> InlineKeyboardMarkup | None:
        return

    async def QrFetched(self, png: bytes, renew: bool = False):
        text = (
            "二维码已刷新:"
            if renew
            else f"二维码已过期, 请重新扫描[{self.qr_times}]"
            if self.qr_times
            else "扫码登陆:"
        )

        self.qr_msg = await self.bot.send_photo(
            self.admin,
            png,
            text,
            disable_notification=False,
            reply_markup=self.qr_markup(),
        )
        self.qr_times += 1

    async def QrFailed(self, msg: str | None = None):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None
        await self.bot.send_message(self.admin, "二维码登录失败" + (f": {msg}" if msg else ""))

    async def QrSucceess(self):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None


class DefaultFeedHook(FeedEvent):
    def __init__(self, queue: EditableQueue, block: list[int]) -> None:
        super().__init__()
        self.queue = queue
        self.block = set(block)
        self.new_batch = self.queue.new_batch

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        logger.debug(f"bid={bid}: {feed}")
        if feed.uin in self.block:
            logger.info(f"Block hit: {feed.uin}")
            return await self.FeedDropped(bid, feed)
        await self.queue.add(bid, feed)

    async def FeedDropped(self, bid: int, feed):
        logger.debug(f"batch {bid}: one feed dropped")

    async def FeedMediaUpdate(self, bid: int, feed: FeedContent):
        logger.debug(f"feed update received: media={feed.media}")
        await self.queue.edit(bid, feed)
