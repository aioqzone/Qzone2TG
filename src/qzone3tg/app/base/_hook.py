from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.utils.formatting import Pre, Text
from aioqzone.model import FeedData
from aioqzone_feed.type import FeedContent

if TYPE_CHECKING:
    from . import BaseApp


def add_up_impls(self: BaseApp):
    from aiogram.utils.formatting import Pre, Text

    @self.login.up.login_failed.add_impl
    async def LoginFailed(uin: int, exc: BaseException | str):
        await self.bot.send_message(self.admin, **Text("密码登录失败 ", Pre(str(exc))).as_kwargs())

    @self.login.up.login_success.add_impl
    async def LoginSuccess(uin: int):
        self.restart_heartbeat()
        await self.bot.send_message(self.admin, "密码登录成功", disable_notification=True)

    try:
        from slide_tc import solve_slide_captcha
    except ImportError:
        self.log.warning("slide_tc is not installed, slide captcha solving not availible")
    else:
        self.login.up.solve_slide_captcha.add_impl(solve_slide_captcha)


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
        if any(await self.is_uin_blocked.results(feed.uin)):
            self.log.info(f"Blocklist hit: {feed.uin}({feed.nickname})")
            return await FeedDropped(bid, feed)

        await self.ch_db_write.wait()
        if feed_mids := await get_mids(feed):
            self.log.info(f"Feed {feed.fid} is sent before. Skipped.", extra=dict(feed=feed))
            self.log.debug(f"mids={feed_mids}")
        else:
            self.queue.add(
                bid,
                feed,
                await get_mids(feed.forward) if isinstance(feed.forward, FeedContent) else None,
            )

    @self.qzone.feed_dropped.add_impl
    async def FeedDropped(bid: int, feed):
        self.log.debug(f"batch {bid}: one feed is dropped")
        self.queue.drop(bid, feed)

    @self.qzone.stop_fetch.add_impl
    async def StopFeedFetch(feed: FeedData) -> bool:
        return await self.store.exists(*FeedOrm.primkey(feed))

    @self.is_uin_blocked.add_impl
    def in_blockset(uin: int):
        return uin in self.blockset


def add_hb_impls(self: BaseApp):
    from aiohttp import ClientResponseError
    from aioqzone.exception import QzoneError
    from tenacity import RetryError

    STOP_HB_EXC = [QzoneError]
    last_fail_cause: BaseException | None = None

    def is_exc_similar(exc1: BaseException, exc2: BaseException) -> bool:
        match exc1:
            case ClientResponseError() if isinstance(exc2, ClientResponseError):
                return (
                    exc1.code == exc2.code
                    and exc1.request_info.url.host == exc2.request_info.url.host
                )
            case _:
                return exc1 == exc2

    def friendly_exc_str(exc: BaseException) -> str:
        match exc:
            case ClientResponseError():
                return f"{exc.__class__.__name__}({exc.status}: {exc.message})"
            case _:
                return str(exc)

    @self.qzone.hb_failed.add_impl
    async def HeartbeatFailed(exc: BaseException):
        # unpack wrapped exceptions
        if isinstance(exc, RetryError):
            exc = exc.last_attempt.result()
        self.log.debug(f"heartbeat failed: {exc}")

        if not any(isinstance(exc, i) for i in STOP_HB_EXC):
            nonlocal last_fail_cause
            if last_fail_cause is None or not is_exc_similar(last_fail_cause, exc):
                last_fail_cause = exc
                return
            else:
                self.log.debug(f"连续两次因{exc.__class__.__name__}心跳异常", exc_info=exc)
                last_fail_cause = None

        self.timers["hb"].pause()
        self.log.warning(f"因{exc.__class__.__name__}暂停心跳")
        await self.bot.send_message(
            self.admin, **Text("心跳已暂停", Pre(friendly_exc_str(exc))).as_kwargs()
        )

    @self.qzone.hb_refresh.add_impl
    async def HeartbeatRefresh(num: int):
        if num <= 0:
            return

        self.log.info(f"Heartbeat triggers a refresh: count={num}")
        if self.fetch_lock.locked():
            self.log.info("当前正在爬取，心跳刷新已忽略。")
            return
        self.ch_fetch.add_awaitable(self._fetch(self.conf.bot.admin, is_period=True))

    @self.qzone.hb_refresh.add_impl
    def clear_last_fail_cause(num: int):
        nonlocal last_fail_cause
        last_fail_cause = None
