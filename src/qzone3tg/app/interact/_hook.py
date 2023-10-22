from __future__ import annotations

import asyncio
from re import Match
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import InteractApp


def add_up_impls(self: InteractApp):
    from aiogram import F, Router
    from aiogram.types import ForceReply, Message

    CA = F.from_user.id.in_({self.conf.bot.admin})
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

    async def force_reply_answer(msg: Message) -> str | None:
        """A hook cannot get answer from the user. This should be done by handler in app.
        So this method should be implemented in app level.

        :param msg: The force reply message to wait for the reply from user.
        :param timeout: wait timeout
        :return: None if timeout, else the reply string.
        """
        nonlocal evt, code
        self.dp.include_router(router)
        try:
            await asyncio.wait_for(evt.wait(), timeout=self.conf.qzone.up_config.vcode_timeout)
        except asyncio.CancelledError:
            return
        except asyncio.TimeoutError:
            await msg.reply("超时未回复")
            return
        else:
            return code
        finally:
            self.dp.sub_routers.remove(router)

    @self._uplogin.sms_code_input.add_impl
    async def GetSmsCode(uin: int, phone: str, nickname: str) -> str | None:
        m = await self.bot.send_message(
            self.admin,
            f"将要登录的是{nickname}，请输入密保手机({phone})上收到的验证码:",
            disable_notification=False,
            reply_markup=ForceReply(input_field_placeholder="012345"),
        )
        code = await force_reply_answer(m)
        if code is None:
            await self.bot.send_message(self.admin, "超时未回复")
            await m.edit_reply_markup(reply_markup=None)
            return

        return code


def add_qr_impls(self: InteractApp):
    from aiogram.types import BufferedInputFile, InputMediaPhoto, Message
    from aiogram.utils.formatting import Pre, Text
    from sqlalchemy.ext.asyncio import AsyncSession

    from qzone3tg.app.storage.loginman import save_cookie

    qr_msg: Message | None = None

    async def _cleanup():
        nonlocal qr_msg
        if isinstance(qr_msg, Message):
            try:
                await qr_msg.delete()
            except BaseException as e:
                self.log.warning(e)
            finally:
                qr_msg = None

    @self._qrlogin.login_failed.add_impl
    async def LoginFailed(uin: int, exc: BaseException | str):
        await _cleanup()
        await self.bot.send_message(self.admin, **Text("二维码登录失败 ", Pre(str(exc))).as_kwargs())

    @self._qrlogin.login_success.add_impl
    async def LoginSuccess(uin: int):
        await self.restart_heartbeat()
        await _cleanup()
        await self.bot.send_message(self.admin, "登录成功")
        self._uplogin.cookie.update(self._qrlogin.cookie)
        async with AsyncSession(self.engine) as sess:
            await save_cookie(self._qrlogin.cookie, self.conf.qzone.uin, sess)

    def _as_inputfile(b: bytes):
        return BufferedInputFile(b, "login_qrcode.png")

    @self._qrlogin.qr_fetched.add_impl
    async def QrFetched(png: bytes, times: int, qr_renew=False):
        nonlocal qr_msg

        if qr_msg is None:
            qr_msg = await self.bot.send_photo(
                self.admin,
                _as_inputfile(png),
                caption="扫码登陆:",
                disable_notification=False,
                reply_markup=self._make_qr_markup(),
            )
        else:
            text = f"二维码已过期, 请重新扫描[{times}]"
            if qr_renew:
                # TODO: qr_renew
                text = "二维码已刷新："
                qr_renew = False

            msg = await self.bot.edit_message_media(
                InputMediaPhoto(media=_as_inputfile(png), caption=text),
                self.admin,
                qr_msg.message_id,
                reply_markup=self._make_qr_markup(),
            )
            if isinstance(msg, Message):
                qr_msg = msg
