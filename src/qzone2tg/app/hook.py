"""Inherits all hooks from aioqzone and implements hook behavior."""

from collections import defaultdict
import logging
from typing import Any, Optional

from aioqzone.interface.hook import Emittable
from aioqzone.interface.hook import Event
from aioqzone.interface.hook import QREvent
from aioqzone.utils.time import sementic_time
from aioqzone_feed.interface.hook import FeedContent
from aioqzone_feed.interface.hook import FeedEvent
from aioqzone_feed.type import BaseFeed
from telegram import Bot
from telegram import InlineKeyboardMarkup
from telegram import Message

from ..bot.limitbot import ChatId
from ..bot.limitbot import LimitedBot
from ..bot.queue import ForwardEvent
from ..bot.queue import MsgBarrier
from ..bot.queue import MsgScheduler
from ..utils.iter import anext
from ..utils.iter import anext_

logger = logging.getLogger(__name__)


class StorageEvent(Event):
    async def SaveFeed(self, feed: BaseFeed, msgs_id: list[int]):
        pass

    async def get_message_id(self, feed: BaseFeed) -> Optional[list[int]]:
        pass

    async def update_message_id(self, feed: BaseFeed, mids: list[int]):
        pass

    async def clean(self, seconds: float):
        pass


class DefaultForwardHook(ForwardEvent, Emittable[StorageEvent]):
    def __init__(self, bot: Bot, admin: ChatId, fwd_map: dict[int, ChatId] = None) -> None:
        super().__init__()
        self.bot = LimitedBot(bot)
        self.admin = admin
        self.forward_map = defaultdict(lambda: admin, fwd_map or {})

    def header(self, feed: FeedContent):
        semt = sementic_time(feed.abstime)
        if feed.forward is None:
            return f"{feed.nickname}于{semt}发布了说说：\n\n"
        if isinstance(feed.forward, BaseFeed):
            return f"{feed.nickname}于{semt}转发了" \
            f"<a href='user.qzone.qq.com/{feed.forward.uin}'>{feed.forward.nickname}</a>的说说：\n\n"
        return f"{feed.nickname}于{semt}分享了<a href='{feed.forward}'>应用</a>：\n\n"

    async def SendNow(self, feed: FeedContent) -> list[int]:
        media = [i.raw for i in feed.media] if feed.media else []
        kw: dict[str, Any] = dict(reply_markup=self.like_markup(feed))

        if isinstance(feed.forward, BaseFeed):
            assert isinstance(feed.forward, FeedContent)
            mids = await self.hook.get_message_id(feed.forward) or await self.SendNow(feed.forward)
            kw['reply_to_message_id'] = mids[0] if mids else None

        content = self.header(feed) + feed.content
        agen = self.bot.unify_send(self.forward_map[feed.uin], content, media, **kw)
        mids = [i.message_id async for i in agen]
        self.add_hook_ref('storage', self.hook.SaveFeed(feed, mids))
        return mids

    async def FeedDroped(self, feed: FeedContent, *exc):
        exc_brf = [str(i) for i in exc]
        logger.error(f"Error in forward: exc={exc_brf}, feed={feed}")
        for i, e in enumerate(exc, start=1):
            logger.debug("Exception in #%d retry:", i, exc_info=e)

    def like_markup(self, feed: BaseFeed) -> Optional[InlineKeyboardMarkup]:
        return


class MediaUpdateHook(DefaultForwardHook):
    async def SendNow(self, feed: FeedContent):
        mids = await self.hook.get_message_id(feed)
        if mids is None: return await super().SendNow(feed)
        assert feed.media
        nmids = await self.bot.edit_media(
            self.forward_map[feed.uin], mids, [i.raw for i in feed.media]
        )
        mids = [n.message_id if isinstance(n, Message) else p for p, n in zip(mids, nmids)]
        self.add_hook_ref('storage', self.hook.update_message_id(feed, mids))

    async def FeedDroped(self, feed: FeedContent, *exc):
        exc_brf = [str(i) for i in exc]
        logger.error(f"Media update error: exc={exc_brf}, media={feed.media}")
        for i, e in enumerate(exc, start=1):
            logger.debug("Exception in #%d retry:", i, exc_info=e)


class DefaultQrHook(QREvent):
    bot: LimitedBot
    admin: ChatId

    def __init__(self) -> None:
        super().__init__()
        self.qr_msg: Optional[Message] = None
        self.lg_msg: Optional[Message] = None
        self.qr_times: int = 0
        """qr sent times"""

    async def LoginFailed(self, msg: str = None):
        await anext(self.bot.send_message(self.admin, text=msg or '登录失败'))

    async def LoginSuccess(self):
        self.lg_msg = await anext_(self.bot.send_message(self.admin, '登录成功'))

    def qr_markup(self) -> Optional[InlineKeyboardMarkup]:
        return

    async def QrFetched(self, png: bytes, renew: bool = False):
        text = '二维码已刷新:' if renew else f'二维码已过期, 请重新扫描[{self.qr_times}]' if self.qr_times else '扫码登陆:'

        agen = self.bot.send_photo(
            self.admin, text, png, disable_notification=False, reply_markup=self.qr_markup()
        )
        self.qr_msg = await anext_(agen)
        self.qr_times += 1

    async def QrFailed(self, msg: str = None):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None
        await anext(self.bot.send_message(self.admin, '二维码登录失败' + (f': {msg}' if msg else '')))

    async def QrSucceess(self):
        self.qr_times = 0
        assert self.qr_msg
        self.qr_msg.delete()
        self.qr_msg = None


class DefaultFeedHook(FeedEvent):
    def __init__(self) -> None:
        super().__init__()
        self.update_scd = MsgBarrier()
        self.new_batch()

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        logger.debug(f"bid={bid}: {feed}")
        self.msg_scd.add(bid, feed)

    async def FeedMediaUpdate(self, feed: FeedContent):
        logger.debug(f"feed update received: media={feed.media}")
        self.update_scd.buffer.add(feed)

    def new_batch(self, val: int = 0, max_retry: int = 2):
        self.msg_scd = MsgScheduler(val, max_retry)


class BaseAppHook(DefaultForwardHook, DefaultQrHook, DefaultFeedHook):
    def __init__(self, bot: Bot, admin: ChatId, fwd_map: dict[int, ChatId] = None) -> None:
        DefaultForwardHook.__init__(self, bot, admin, fwd_map)
        DefaultQrHook.__init__(self)
        DefaultFeedHook.__init__(self)

    async def SendNow(self, feed: FeedContent):
        # Remove the feed from media-update pending buffer for it has not been sent.
        # And just send it as usual is okay since the feed obj is updated at the moment.
        if feed in self.update_scd.buffer:
            self.update_scd.buffer.remove(feed)
        return await super().SendNow(feed)

    def new_batch(self, val: int = 0, max_retry: int = 2):
        super().new_batch(val, max_retry)
        self.msg_scd.register_hook(self)

    async def send_all(self):
        try:
            await self.msg_scd.send_all()
        finally:
            self.new_batch()
        self.update_scd.send_all()