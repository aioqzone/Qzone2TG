from __future__ import annotations

from typing import TYPE_CHECKING

from aioqzone.model import FeedData

from qzone3tg.bot.splitter import html_trans

if TYPE_CHECKING:
    from aioqzone.model.response.web import FeedRep
    from aioqzone_feed.type import FeedContent

    from . import BaseApp


def qrevent_hook(app: BaseApp):
    from aiogram import InputMediaPhoto, Message
    from aioqzone.api import LoginMethod

    async def _cleanup():
        context: dict = app.dp.bot_data
        context["qr_renew"] = False

        if isinstance(qr_msg := context.get("qr_msg"), Message):
            context["qr_msg"] = None
            try:
                await qr_msg.delete()
            except BaseException as e:
                app.log.warning(e)

    async def LoginFailed(uin: int, method: LoginMethod, exc: str):
        if method != "qr":
            return
        await _cleanup()
        pmsg = f": {exc.translate(html_trans)}" if exc else ""
        await app.bot.send_message(app.admin, "二维码登录失败" + pmsg)

    async def LoginSuccess(uin: int, method: LoginMethod):
        if method != "qr":
            return
        await app.restart_heartbeat()
        await _cleanup()
        await app.bot.send_message(app.admin, "登录成功")

    async def QrFetched(png: bytes, times: int):
        context: dict = app.dp.bot_data

        if (msg := context.get("qr_msg")) is None:
            context["qr_msg"] = await app.bot.send_photo(
                app.admin,
                png,
                "扫码登陆:",
                disable_notification=False,
                reply_markup=app._make_qr_markup(),
            )
        else:
            text = f"二维码已过期, 请重新扫描[{times}]"
            if context.get("qr_renew"):
                text = "二维码已刷新："
                context["qr_renew"] = False

            assert isinstance(msg, Message)
            msg = await app.bot.edit_message_media(
                InputMediaPhoto(png, text),
                app.admin,
                msg.message_id,
                reply_markup=app._make_qr_markup(),
            )
            if isinstance(msg, Message):
                context["qr_msg"] = msg

    app.loginman.login_failed.add_impl(LoginFailed)
    app.loginman.login_success.add_impl(LoginSuccess)
    app.loginman.qr_fetched.add_impl(QrFetched)


def upevent_hook(app: BaseApp):
    from aioqzone.api import LoginMethod

    async def LoginFailed(uin: int, method: LoginMethod, exc: str):
        if method != "up":
            return
        pmsg = f": {exc.translate(html_trans)}" if exc else ""
        await app.bot.send_message(app.admin, "密码登录失败" + pmsg)

    async def LoginSuccess(uin: int, method: LoginMethod):
        if method != "up":
            return
        await app.restart_heartbeat()
        await app.bot.send_message(app.admin, "登录成功", disable_notification=True)

    app.loginman.login_failed.add_impl(LoginFailed)
    app.loginman.login_success.add_impl(LoginSuccess)


def feedevent_hook(app: BaseApp):
    from aioqzone_feed.type import BaseFeed

    from ..storage.orm import FeedOrm, MessageOrm

    block = set(app.conf.qzone.block or ())
    if app.conf.qzone.block_self:
        block.add(app.conf.qzone.uin)
    app.blockset = block

    async def get_mids(feed: BaseFeed) -> list[int]:
        """Get a list of message id from storage.

        :param feed: feed
        :return: the list of message id associated with this feed, or None if not found.
        """
        r = await app.store.get_msg_orms(*MessageOrm.fkey(feed))
        return [i.mid for i in r]

    async def FeedProcEnd(bid: int, feed: FeedContent):
        app.log.debug(f"bid={bid}: {feed}")
        if feed.uin in app.blockset:
            app.log.info(f"Blocklist hit: {feed.uin}({feed.nickname})")
            return await FeedDropped(bid, feed)

        await app.ch_db_write.wait()
        if await get_mids(feed):
            app.queue.add(
                bid,
                feed,
                await get_mids(feed.forward) if isinstance(feed.forward, FeedContent) else None,
            )

    async def FeedDropped(bid: int, feed):
        app.log.debug(f"batch {bid}: one feed is dropped")
        app.queue.skip_num += 1

    async def FeedMediaUpdate(bid: int, feed: FeedContent):
        app.log.warning(f"FeedMediaUpdate is deprecated in h5 version. media={feed.media}")

    async def StopFeedFetch(feed: FeedRep | FeedData) -> bool:
        return await app.store.exists(*FeedOrm.primkey(feed))

    app.qzone.feed_processed.add_impl(FeedProcEnd)
    app.qzone.feed_dropped.add_impl(FeedDropped)
    app.qzone.feed_media_updated.add_impl(FeedMediaUpdate)
    app.qzone.stop_fetch = StopFeedFetch


def heartbeatevent_hook(app: BaseApp):
    from aioqzone.exception import QzoneError

    async def HeartbeatFailed(exc: BaseException, stop: bool):
        app.log.debug(f"heartbeat failed: {exc}")
        if isinstance(exc, QzoneError) and "登录" in exc.msg:
            assert app.dp.job_queue
            app.dp.job_queue.run_once(app.restart_heartbeat, 300)

    async def HeartbeatRefresh(num: int):
        app.log.info(f"Heartbeat triggers a refresh: count={num}")
        if app.ch_fetch._futs:
            app.log.warning("fetch taskset should contain only one task, heartbeat fetch skipped.")
            app.log.debug(app.ch_fetch._futs)
            return
        app.ch_fetch.add_awaitable(app._fetch(app.conf.bot.admin, is_period=True))

    app.qzone.hb_api.hb_failed.add_impl(HeartbeatFailed)
    app.qzone.hb_api.hb_refresh.add_impl(HeartbeatRefresh)
