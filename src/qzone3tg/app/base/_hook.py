from __future__ import annotations

from typing import TYPE_CHECKING

from aioqzone.model import FeedData
from aioqzone_feed.type import FeedContent

from qzone3tg.bot.splitter import html_trans

if TYPE_CHECKING:
    from . import BaseApp


def qrevent_hook(app: BaseApp):
    from aiogram.types import BufferedInputFile, InputMediaPhoto, Message

    qr_msg: Message | None = None

    async def _cleanup():
        nonlocal qr_msg
        if isinstance(qr_msg, Message):
            try:
                await qr_msg.delete()
            except BaseException as e:
                app.log.warning(e)
            finally:
                qr_msg = None

    async def LoginFailed(uin: int, exc: BaseException | str):
        await _cleanup()
        exc = str(exc)
        pmsg = f": {exc.translate(html_trans)}" if exc else ""
        await app.bot.send_message(app.admin, "二维码登录失败" + pmsg)

    async def LoginSuccess(uin: int):
        await app.restart_heartbeat()
        await _cleanup()
        await app.bot.send_message(app.admin, "登录成功")
        app._uplogin.cookie.update(app._qrlogin.cookie)

    def _as_inputfile(b: bytes):
        return BufferedInputFile(b, "login_qrcode.png")

    async def QrFetched(png: bytes, times: int, qr_renew=False):
        nonlocal qr_msg

        if qr_msg is None:
            qr_msg = await app.bot.send_photo(
                app.admin,
                _as_inputfile(png),
                caption="扫码登陆:",
                disable_notification=False,
                reply_markup=app._make_qr_markup(),
            )
        else:
            text = f"二维码已过期, 请重新扫描[{times}]"
            if qr_renew:
                # TODO: qr_renew
                text = "二维码已刷新："
                qr_renew = False

            msg = await app.bot.edit_message_media(
                InputMediaPhoto(media=_as_inputfile(png), caption=text),
                app.admin,
                qr_msg.message_id,
                reply_markup=app._make_qr_markup(),
            )
            if isinstance(msg, Message):
                qr_msg = msg

    app._qrlogin.login_failed.add_impl(LoginFailed)
    app._qrlogin.login_success.add_impl(LoginSuccess)
    app._qrlogin.qr_fetched.add_impl(QrFetched)


def upevent_hook(app: BaseApp):
    async def LoginFailed(uin: int, exc: BaseException | str):
        exc = str(exc)
        pmsg = f": {exc.translate(html_trans)}" if exc else ""
        await app.bot.send_message(app.admin, "密码登录失败" + pmsg)

    async def LoginSuccess(uin: int):
        await app.restart_heartbeat()
        await app.bot.send_message(app.admin, "登录成功", disable_notification=True)

        app._qrlogin.cookie.update(app._uplogin.cookie)

    app._uplogin.login_failed.add_impl(LoginFailed)
    app._uplogin.login_success.add_impl(LoginSuccess)


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

    async def StopFeedFetch(feed: FeedData) -> bool:
        return await app.store.exists(*FeedOrm.primkey(feed))

    app.qzone.feed_processed.add_impl(FeedProcEnd)
    app.qzone.feed_dropped.add_impl(FeedDropped)
    app.qzone.stop_fetch = StopFeedFetch


def heartbeatevent_hook(app: BaseApp):
    from aioqzone.exception import QzoneError

    STOP_HB_EXC = []

    async def HeartbeatFailed(exc: BaseException):
        app.log.debug(f"heartbeat failed: {exc}")
        if any(isinstance(exc, i) for i in STOP_HB_EXC):
            app.timers["hb"].pause()
            app.log.warning(f"因{exc.__class__.__name__}暂停心跳")

    async def HeartbeatRefresh(num: int):
        app.log.info(f"Heartbeat triggers a refresh: count={num}")
        if app.fetch_lock.locked():
            app.log.warning("fetch taskset should contain only one task, heartbeat fetch skipped.")
            return
        app.ch_fetch.add_awaitable(app._fetch(app.conf.bot.admin, is_period=True))

    app.qzone.hb_failed.add_impl(HeartbeatFailed)
    app.qzone.hb_refresh.add_impl(HeartbeatRefresh)
