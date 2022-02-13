"""Defines all hooks used in Qzone3TG and implements some default hook.
"""

import asyncio
from collections import defaultdict
import logging
from typing import Any, Optional

from aiohttp import ClientSession
from aioqzone.interface.hook import QREvent
from aioqzone.utils.time import sementic_time
from aioqzone_feed.interface.hook import FeedContent
from aioqzone_feed.interface.hook import FeedEvent
from aioqzone_feed.type import BaseFeed
from telegram import Bot
from telegram import InlineKeyboardMarkup
from telegram import Message
from telegram.error import BadRequest
from telegram.error import TimedOut

from qzone3tg.bot.limitbot import ChatId
from qzone3tg.bot.limitbot import FetchBot
from qzone3tg.bot.queue import ForwardEvent
from qzone3tg.bot.queue import MsgBarrier
from qzone3tg.bot.queue import MsgScheduler
from qzone3tg.utils.iter import anext
from qzone3tg.utils.iter import anext_

logger = logging.getLogger(__name__)


class DefaultForwardHook(ForwardEvent):
    def __init__(self, bot: FetchBot, fwd_map: dict[int, ChatId]) -> None:
        ForwardEvent.__init__(self)
        self.bot = bot
        self.forward_map = fwd_map

    def header(self, feed: FeedContent):
        href = lambda t, u: f"<a href='{u}'>{t}</a>"
        semt = sementic_time(feed.abstime)
        nickname = href(feed.nickname, f"user.qzone.qq.com/{feed.uin}")

        if feed.forward is None:
            return f"{nickname}{semt}发布了{href('说说', str(feed.unikey))}：\n\n"

        if isinstance(feed.forward, BaseFeed):
            return f"{nickname}{semt}转发了" \
            f"{href(feed.forward.nickname, f'user.qzone.qq.com/{feed.forward.uin}')}" \
            f"的{href('说说', str(feed.unikey))}：\n\n"

        share = str(feed.forward)
        return f"{nickname}{semt}分享了{href('应用', share)}：\n\n"

    async def SendNow(
        self,
        feed: FeedContent,
        dep: asyncio.Task[list[int]] = None,
        last_exc: BaseException = None,
    ) -> list[int]:
        dep_exc = mids = None
        if dep:
            try:
                mids = await dep
            except BaseException as e:
                dep_exc = e
        if isinstance(last_exc, TimedOut):
            self.bot.fetcher.timeout()

        kw: dict[str, Any] = dict(
            text=self.header(feed) + feed.content,
            medias=feed.media,
            fetch=isinstance(last_exc, BadRequest)
        )
        if feed.media is None or len(feed.media) <= 1:
            kw['reply_markup'] = self.like_markup(feed)

        if isinstance(feed.forward, BaseFeed):
            if dep_exc:
                logger.warning('Forwardee raise an error. Send forwarder for all.')
                # raise dep_exc
            elif dep is None:
                await self.wait('storage')
                mids = await self.hook.get_message_id(feed.forward)
            kw['reply_to_message_id'] = mids[0] if mids else None

        agen = await self.bot.unify_send(self.forward_map[feed.uin], **kw)
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
    async def SendNow(
        self,
        feed: FeedContent,
        dep: asyncio.Task[list[int]] = None,
        last_exc: BaseException = None,
    ):
        if isinstance(last_exc, TimedOut):
            self.bot.fetcher.timeout()

        mids = await self.hook.get_message_id(feed)
        if mids is None: return await super().SendNow(feed)
        assert feed.media
        nmids = await self.bot.edit_media(
            self.forward_map[feed.uin],
            mids,
            feed.media,
            fetch=isinstance(last_exc, BadRequest),
        )
        mids = [n.message_id if isinstance(n, Message) else p for p, n in zip(mids, nmids)]
        self.add_hook_ref('storage', self.hook.update_message_id(feed, mids))

    async def FeedDroped(self, feed: FeedContent, *exc):
        exc_brf = [str(i) for i in exc]
        logger.error(f"Media update error: exc={exc_brf}, media={feed.media}")
        for i, e in enumerate(exc, start=1):
            logger.debug("Exception in #%d retry:", i, exc_info=e)


class DefaultQrHook(QREvent):
    def __init__(self, admin: ChatId, bot: FetchBot) -> None:
        QREvent.__init__(self)
        self.admin = admin
        self.bot = bot
        self.qr_msg: Optional[Message] = None
        self.lg_msg: Optional[Message] = None
        self.qr_times: int = 0
        """qr sent times"""

    async def LoginFailed(self, msg: str = None):
        pass

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
    def __init__(self, block: list[int]) -> None:
        super().__init__()
        self.update_scd = MsgBarrier()
        self.block = set(block)
        self.new_batch()

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        logger.debug(f"bid={bid}: {feed}")
        if feed.uin in self.block:
            logger.info(f'Block hit: {feed.uin}')
            return
        await self.msg_scd.add(bid, feed)

    async def FeedMediaUpdate(self, feed: FeedContent):
        logger.debug(f"feed update received: media={feed.media}")
        self.update_scd.buffer.add(feed)

    def new_batch(self, val: int = 0, max_retry: int = 2):
        self.msg_scd = MsgScheduler(val, max_retry)


class BaseAppHook(DefaultForwardHook, DefaultQrHook, DefaultFeedHook):
    def __init__(
        self,
        sess: ClientSession,
        bot: Bot,
        admin: ChatId,
        block: list[int] = None,
        fwd_map: dict[int, ChatId] = None,
        freq_limit: int = 30,
        send_gif_as_anim: bool = False,
    ) -> None:
        fetchbot = FetchBot(sess, bot, freq_limit, send_gif_as_anim)
        DefaultForwardHook.__init__(self, fetchbot, defaultdict(lambda: admin, fwd_map or {}))
        DefaultQrHook.__init__(self, admin, fetchbot)
        DefaultFeedHook.__init__(self, block or [])
        self.update_scd.register_hook(MediaUpdateHook(fetchbot, self.forward_map))

    async def SendNow(
        self,
        feed: FeedContent,
        dep: asyncio.Task[list[int]] = None,
        last_exc: BaseException = None,
    ):
        # Remove the feed from media-update pending buffer for it has not been sent.
        # And just send it as usual is okay since the feed obj is updated at the moment.
        if feed in self.update_scd.buffer:
            self.update_scd.buffer.remove(feed)
        return await super().SendNow(feed, dep, last_exc)

    def new_batch(self, val: int = 0, max_retry: int = 2):
        super().new_batch(val, max_retry)
        self.msg_scd.register_hook(self)

    async def send_all(self):
        await self.msg_scd.send_all()
        self.update_scd.send_all()
