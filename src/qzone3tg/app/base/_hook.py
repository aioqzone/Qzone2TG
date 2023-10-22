from __future__ import annotations

from typing import TYPE_CHECKING

from aioqzone.model import FeedData
from aioqzone_feed.type import FeedContent

if TYPE_CHECKING:
    from . import BaseApp


def add_up_impls(self: BaseApp):
    from aiogram.utils.formatting import Pre, Text
    from sqlalchemy.ext.asyncio import AsyncSession

    from qzone3tg.app.storage.loginman import save_cookie

    @self._uplogin.login_failed.add_impl
    async def LoginFailed(uin: int, exc: BaseException | str):
        await self.bot.send_message(self.admin, **Text("密码登录失败 ", Pre(str(exc))).as_kwargs())

    @self._uplogin.login_success.add_impl
    async def LoginSuccess(uin: int):
        await self.restart_heartbeat()
        await self.bot.send_message(self.admin, "登录成功", disable_notification=True)

        self._qrlogin.cookie.update(self._uplogin.cookie)
        async with AsyncSession(self.engine) as sess:
            await save_cookie(self._qrlogin.cookie, self.conf.qzone.uin, sess)


def add_feed_impls(self: BaseApp):
    from aioqzone_feed.type import BaseFeed

    from ..storage.orm import FeedOrm, MessageOrm

    block = set(self.conf.qzone.block or ())
    if self.conf.qzone.block_self:
        block.add(self.conf.qzone.uin)
    self.blockset = block

    async def get_mids(feed: BaseFeed) -> list[int]:
        """Get a list of message id from storage.

        :param feed: feed
        :return: the list of message id associated with this feed, or None if not found.
        """
        r = await self.store.get_msg_orms(*MessageOrm.fkey(feed))
        return [i.mid for i in r]

    @self.qzone.feed_processed.add_impl
    async def FeedProcEnd(bid: int, feed: FeedContent):
        self.log.debug(f"bid={bid}: {feed}")
        if feed.uin in self.blockset:
            self.log.info(f"Blocklist hit: {feed.uin}({feed.nickname})")
            return await FeedDropped(bid, feed)

        await self.ch_db_write.wait()
        if await get_mids(feed):
            self.queue.add(
                bid,
                feed,
                await get_mids(feed.forward) if isinstance(feed.forward, FeedContent) else None,
            )

    @self.qzone.feed_dropped.add_impl
    async def FeedDropped(bid: int, feed):
        self.log.debug(f"batch {bid}: one feed is dropped")
        self.queue.drop(bid, feed)

    async def StopFeedFetch(feed: FeedData) -> bool:
        return await self.store.exists(*FeedOrm.primkey(feed))

    self.qzone.stop_fetch = StopFeedFetch


def add_hb_impls(self: BaseApp):
    from aioqzone.exception import QzoneError

    STOP_HB_EXC = []

    @self.qzone.hb_failed.add_impl
    async def HeartbeatFailed(exc: BaseException):
        self.log.debug(f"heartbeat failed: {exc}")
        if any(isinstance(exc, i) for i in STOP_HB_EXC):
            self.timers["hb"].pause()
            self.log.warning(f"因{exc.__class__.__name__}暂停心跳")

    @self.qzone.hb_refresh.add_impl
    async def HeartbeatRefresh(num: int):
        self.log.info(f"Heartbeat triggers a refresh: count={num}")
        if self.fetch_lock.locked():
            self.log.warning(
                "fetch taskset should contain only one task, heartbeat fetch skipped."
            )
            return
        self.ch_fetch.add_awaitable(self._fetch(self.conf.bot.admin, is_period=True))
