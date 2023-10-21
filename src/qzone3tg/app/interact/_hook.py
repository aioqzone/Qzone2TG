from __future__ import annotations

import asyncio
from re import Match
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import InteractApp


def upevent_hook(app: InteractApp):
    from aiogram import F, Router
    from aiogram.types import ForceReply, Message

    CA = F.from_user.id.in_({app.conf.bot.admin})
    router = Router(name="input")

    code: str = ""
    evt = asyncio.Event()

    @router.message(CA, F.message.regexp(r"\s*(\d{6})\s*").as_("input_code"))
    async def _input_verify_code(message: Message, input_code: Match[str]):
        nonlocal code, evt
        code = input_code.group(1)
        evt.set()

    @router.message(CA)
    async def _wrong_verify_code(message: Message):
        await message.reply("应回复六位数字验证码")

    async def GetSmsCode(uin: int, phone: str, nickname: str) -> str | None:
        m = await app.bot.send_message(
            app.admin,
            f"将要登录的是{nickname}，请输入密保手机({phone})上收到的验证码:",
            disable_notification=False,
            reply_markup=ForceReply(input_field_placeholder="012345"),
        )
        code = await force_reply_answer(m)
        if code is None:
            await app.bot.send_message(app.admin, "超时未回复")
            await m.edit_reply_markup(reply_markup=None)
            return

        return code

    async def force_reply_answer(msg: Message) -> str | None:
        """A hook cannot get answer from the user. This should be done by handler in app.
        So this method should be implemented in app level.

        :param msg: The force reply message to wait for the reply from user.
        :param timeout: wait timeout
        :return: None if timeout, else the reply string.
        """
        nonlocal evt, code
        app.dp.include_router(router)
        try:
            await asyncio.wait_for(evt.wait(), timeout=app.conf.qzone.vcode_timeout)
        except asyncio.CancelledError:
            return
        except asyncio.TimeoutError:
            await msg.reply("超时未回复")
            return
        else:
            return code
        finally:
            app.dp.sub_routers.remove(router)

    app._uplogin.sms_code_input.add_impl(GetSmsCode)
