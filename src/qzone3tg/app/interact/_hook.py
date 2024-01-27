from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import InteractApp


def add_up_impls(self: InteractApp):
    from aiogram import F
    from aiogram.types import BufferedInputFile, ForceReply
    from aiogram.utils.media_group import MediaGroupBuilder

    CA = F.from_user.id.in_({self.conf.bot.admin})

    @self.login.up.sms_code_input.add_impl
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

    @self.login.up.solve_select_captcha.add_impl
    async def GetSelectCaptcha(prompt: str, imgs: tuple[bytes, ...]) -> list[int]:
        n = len(imgs)
        assert n < 10
        builder = MediaGroupBuilder(caption=prompt)
        for i, b in enumerate(imgs):
            builder.add_photo(BufferedInputFile(b, f"select_captcha_{i}.png"))

        _m = await self.bot.send_media_group(self.admin, builder.build())
        m = await self.bot.send_message(
            self.admin,
            f"请输入1~{n}之间的数字，如有多个可连续输入，或用逗号或空格分隔",
            disable_notification=False,
            reply_to_message_id=_m[0].message_id,
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
        await self.bot.delete_messages(self.admin, [i.message_id for i in _m])

        if ans is None:
            return []
        ans = re.sub(r"[\s,]", "", ans)
        return [int(c) for c in ans]


def add_qr_impls(self: InteractApp):
    from aiogram.types import BufferedInputFile, InputMediaPhoto, Message
    from aiogram.utils.formatting import BotCommand as CommandText
    from aiogram.utils.formatting import Pre, Text

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

    @self.login.qr.login_failed.add_impl
    async def LoginFailed(uin: int, exc: BaseException | str):
        await _cleanup()
        await self.bot.send_message(
            self.admin, **Text("二维码登录失败 ", Pre(str(exc))).as_kwargs()
        )

    @self.login.qr.login_success.add_impl
    async def LoginSuccess(uin: int):
        self.restart_heartbeat()
        await asyncio.gather(
            _cleanup(),
            self.bot.send_message(
                self.admin,
                **Text("二维码登录成功，发送 ", CommandText("/start"), " 刷新").as_kwargs(),
            ),
        )

    def _as_inputfile(b: bytes):
        return BufferedInputFile(b, "login_qrcode.png")

    @self.login.qr.qr_fetched.add_impl
    async def QrFetched(png: bytes | None, times: int, qr_renew=False):
        nonlocal qr_msg
        inlinekb = self._make_qr_markup()

        if qr_msg is None:
            if png is None:
                qr_msg = await self.bot.send_message(
                    self.admin,
                    text="二维码已推送到您的QQ手机端，请确认登录。",
                    disable_notification=False,
                    reply_markup=inlinekb,
                )
            else:
                qr_msg = await self.bot.send_photo(
                    self.admin,
                    _as_inputfile(png),
                    caption="请扫码登录",
                    disable_notification=False,
                    reply_markup=inlinekb,
                )
            return

        if qr_renew:
            # TODO: qr_renew
            text = f"二维码已刷新[{times}]"
        else:
            text = f"二维码已过期, 请重新扫描[{times}]"

        if png is None:
            msg = await qr_msg.edit_text(text, reply_markup=inlinekb)
        else:
            msg = qr_msg.edit_media(
                InputMediaPhoto(media=_as_inputfile(png), caption=text),
                reply_markup=inlinekb,
            )

        if isinstance(msg, Message):
            qr_msg = msg
