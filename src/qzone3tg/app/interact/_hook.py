from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import InteractApp


def add_up_impls(self: InteractApp):
    from aiogram import F
    from aiogram.types import BufferedInputFile, ForceReply
    from aiogram.utils.media_group import MediaGroupBuilder

    CA = F.from_user.id.in_({self.conf.bot.admin})

    @self._uplogin.sms_code_input.add_impl
    async def GetSmsCode(uin: int, phone: str, nickname: str) -> str | None:
        m = await self.bot.send_message(
            self.admin,
            f"将要登录的是{nickname}，请输入密保手机({phone})上收到的验证码:",
            disable_notification=False,
            reply_markup=ForceReply(input_field_placeholder="012345"),
        )
        CR = F.reply_to_message.message_id == m.message_id
        return await self.input(
            prompt_message=m,
            pattern=r"\s*(\d{6})\s*",
            retry_prompt="应输入六位数字验证码，当前输入：{text}",
            timeout=self.conf.qzone.up_config.vcode_timeout,
            filters=(CA, CR),
        )

    @self._uplogin.solve_select_captcha.add_impl
    async def GetSelectCaptcha(prompt: str, imgs: tuple[bytes, ...]) -> list[int]:
        n = len(imgs)
        assert n < 10
        builder = MediaGroupBuilder(caption=prompt)
        for i, b in enumerate(imgs):
            builder.add_photo(BufferedInputFile(b, f"select_captcha_{i}.png"))

        await self.bot.send_media_group(self.admin, builder.build())
        m = await self.bot.send_message(
            self.admin,
            f"请输入1~{n}之间的数字，如有多个可连续输入，或用逗号或空格分隔",
            disable_notification=False,
            reply_markup=ForceReply(input_field_placeholder="1,23,456,"),
        )
        CR = F.reply_to_message.message_id == m.message_id

        ans = await self.input(
            m,
            pattern=rf"^([\s,1-{n}]+?)$",
            retry_prompt="请输入1~%d之间的数字，如分隔请使用英文逗号或空格。当前输入：{text}" % n,
            timeout=self.conf.qzone.up_config.vcode_timeout,
            filters=(CA, CR),
        )
        if ans is None:
            return []
        ans = re.sub(r"[\s,]", "", ans)
        return [int(c) for c in ans]


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
