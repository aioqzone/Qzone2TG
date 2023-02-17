from __future__ import annotations

import asyncio
from time import time
from typing import TYPE_CHECKING, Optional

import telegram
from aioqzone.api.loginman import QrStrategy
from aioqzone.event.login import QREvent, UPEvent
from aioqzone_feed.event import FeedEvent
from aioqzone_feed.type import FeedContent
from telegram import InlineKeyboardMarkup, InputMediaPhoto, Message

if TYPE_CHECKING:
    from . import BaseApp


def qrevent_hook(_self: BaseApp, base: type[QREvent]):
    class baseapp_qrevent(base):
        async def LoginFailed(self, meth, msg: Optional[str] = None):
            await super().LoginFailed(meth, msg)
            _self.loginman.suppress_qr_till = time() + _self.loginman.qr_suppress_sec
            await self._cleanup()
            pmsg = f": {msg}" if msg else ""
            await _self.bot.send_message(_self.admin, "二维码登录失败" + pmsg)

        async def LoginSuccess(self, meth):
            await super().LoginSuccess(meth)
            _self.loginman.suppress_qr_till = time() + _self.loginman.qr_suppress_sec
            await _self.restart_heartbeat()
            await self._cleanup()
            await _self.bot.send_message(_self.admin, "登录成功")

        def qr_markup(self) -> InlineKeyboardMarkup | None:
            return

        async def QrFetched(self, png: bytes, times: int):
            context: dict = _self.app.bot_data

            if context.get("qr_msg") is None:
                context["qr_msg"] = await _self.bot.send_photo(
                    _self.admin,
                    png,
                    "扫码登陆:",
                    disable_notification=False,
                    reply_markup=self.qr_markup(),
                )
            else:
                text = f"二维码已过期, 请重新扫描[{times}]"
                if context.get("qr_renew"):
                    text = "二维码已刷新："
                    context["qr_renew"] = False

                msg = await _self.bot.edit_message_media(
                    InputMediaPhoto(png, text),
                    _self.admin,
                    context["qr_msg"].message_id,
                    reply_markup=self.qr_markup(),
                )
                if isinstance(msg, Message):
                    context["qr_msg"] = msg

        async def _cleanup(self):
            context: dict = _self.app.bot_data
            context["qr_renew"] = False

            if isinstance(context.get("qr_msg"), Message):
                try:
                    await context["qr_msg"].delete()
                except BaseException as e:
                    _self.log.warning(e)
                finally:
                    self.qr_msg = None

    return baseapp_qrevent


def upevent_hook(_self: BaseApp, base: type[UPEvent]):
    class baseapp_upevent(base):
        async def LoginFailed(self, meth, msg: Optional[str] = None):
            await super().LoginFailed(meth, msg)
            _self.loginman.suppress_up_till = time() + _self.loginman.up_suppress_sec
            pmsg = f": {msg}" if msg else ""
            await _self.bot.send_message(_self.admin, "密码登录失败" + pmsg)

        async def LoginSuccess(self, meth):
            await super().LoginSuccess(meth)
            await _self.restart_heartbeat()
            await _self.bot.send_message(_self.admin, "登录成功", disable_notification=True)

        async def GetSmsCode(self, phone: str, nickname: str) -> Optional[str]:
            m = await _self.bot.send_message(
                _self.admin,
                f"将要登录的是{nickname}，请输入密保手机({phone})上收到的验证码:",
                disable_notification=False,
                reply_markup=telegram.ForceReply(input_field_placeholder="012345"),
            )
            code = await self.force_reply_answer(m)
            if code is None:
                await _self.bot.send_message(_self.admin, "超时未回复")
                await m.edit_reply_markup(reply_markup=None)
                return

            if len(code) != 6:
                await _self.bot.send_message(_self.admin, "应回复六位数字验证码")
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

    return baseapp_upevent


def feedevent_hook(_self: BaseApp, base: type[FeedEvent]):
    class baseapp_feedevent(FeedEvent):
        def __init__(self) -> None:
            super().__init__()

            self.block = set(_self.conf.qzone.block or ())
            if _self.conf.qzone.block_self:
                self.block.add(_self.conf.qzone.uin)

        async def FeedProcEnd(self, bid: int, feed: FeedContent):
            _self.log.debug(f"bid={bid}: {feed}")
            if feed.uin in self.block:
                _self.log.info(f"Blocklist hit: {feed.uin}({feed.nickname})")
                return await self.FeedDropped(bid, feed)
            await _self.queue.add(bid, feed)

        async def FeedDropped(self, bid: int, feed):
            _self.log.debug(f"batch {bid}: one feed dropped")
            _self.queue.skip_num += 1

        async def FeedMediaUpdate(self, bid: int, feed: FeedContent):
            _self.log.debug(f"feed update received: media={feed.media}")
            await _self.queue.edit(bid, feed)

        async def HeartbeatFailed(self, exc: Optional[BaseException] = None):
            _self.log.debug(f"heartbeat failed: {exc}")
            lm = _self.loginman
            qr_avil = lm.strategy != QrStrategy.forbid and not lm.qr_suppressed
            up_avil = lm.strategy != QrStrategy.force and not lm.up_suppressed
            if qr_avil or up_avil:
                try:
                    await _self.loginman.new_cookie()
                except:
                    return
                else:
                    await _self.restart_heartbeat()
                return

            _self.log.warning("All login methods suppressed and heartbeat failed.")

            info = f"({exc})" if exc else ""
            await _self.bot.send_message(_self.admin, "由于距上次登录的时间间隔少于您所指定的最小值，自动登录已暂停。" + info)

        async def HeartbeatRefresh(self, num: int):
            _self.log.info(f"Heartbeat triggers a refresh: count={num}")
            await _self.fetch(_self.conf.bot.admin, is_period=True)

    return baseapp_feedevent
