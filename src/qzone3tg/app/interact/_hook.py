from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import InteractApp


def upevent_hook(app: InteractApp):
    from aiogram import filters
    from aiogram.types import ForceReply, Message, Update

    class ReplyHandler(MessageHandler):
        def __init__(self, filters, callback, reply: Message):
            super().__init__(filters, callback)
            self.reply = reply

        def check_update(self, update: Update):
            if super().check_update(update) is False:
                return False
            msg = update.effective_message
            assert msg

            if msg.reply_to_message and msg.reply_to_message.message_id == self.reply.message_id:
                return
            return False

    async def GetSmsCode(uin: int, phone: str, nickname: str) -> str | None:
        m = await app.bot.send_message(
            app.admin,
            f"将要登录的是{nickname}，请输入密保手机({phone})上收到的验证码:",
            disable_notification=False,
            reply_markup=ForceReply(input_field_placeholder="012345"),
        )
        code = await self.force_reply_answer(m)
        if code is None:
            await app.bot.send_message(app.admin, "超时未回复")
            await m.edit_reply_markup(reply_markup=None)
            return

        if len(code) != 6:
            await app.bot.send_message(app.admin, "应回复六位数字验证码")
            await m.edit_reply_markup(reply_markup=None)
            return
        return code

    async def force_reply_answer(msg) -> str | None:
        """A hook cannot get answer from the user. This should be done by handler in app.
        So this method should be implemented in app level.

        :param msg: The force reply message to wait for the reply from user.
        :param timeout: wait timeout
        :return: None if timeout, else the reply string.
        """
        code = ""
        evt = asyncio.Event()

        def cb(update: Update, _):
            nonlocal code
            assert update.effective_message
            code = update.effective_message.text or ""
            code = code.strip()
            evt.set()

        handler = ReplyHandler(filters.Regex(r"^\s*\d{6}\s*$"), cb, msg)
        app.dp.add_handler(handler)

        try:
            await asyncio.wait_for(evt.wait(), timeout=app.conf.qzone.vcode_timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return
        else:
            return code
        finally:
            app.dp.remove_handler(handler)

    app._uplogin.sms_code_input.add_impl(GetSmsCode)
