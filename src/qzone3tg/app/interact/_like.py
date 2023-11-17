from __future__ import annotations

from copy import deepcopy
from itertools import chain
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters.command import CommandObject
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.formatting import BotCommand as CommandText
from aiogram.utils.formatting import Pre, Text
from aioqzone.exception import QzoneError
from aioqzone.model import LikeData, PersudoCurkey
from qqqr.utils.iter import firstn

from ..storage.orm import FeedOrm
from .types import SerialCbData

if TYPE_CHECKING:
    from . import InteractApp


async def like_core(self: InteractApp, key: str | int, like=True) -> str | None:
    match key:
        case str():
            feed = await self.store.get_feed_orm(*FeedOrm.primkey(PersudoCurkey.from_str(key)))
        case int():
            feed = await self.Mid2Feed(key)

    if feed is None:
        return f"未找到该消息，可能已超出{self.conf.bot.storage.keepdays}天"

    if feed.unikey is None:
        return "该说说不支持点赞"

    try:
        await self.qzone.internal_dolike_app(
            feed.appid,
            unikey=feed.unikey,
            curkey=feed.curkey or LikeData.persudo_curkey(feed.uin, feed.abstime),
            like=like,
        )
    except QzoneError as e:
        return e.msg


async def btn_like(self: InteractApp, query: CallbackQuery, callback_data: SerialCbData):
    err_msg = await like_core(
        self, str(callback_data.sub_command), callback_data.command == "like"
    )
    if err_msg is not None:
        await query.answer(text="点赞失败：" + err_msg, show_alert=True)
        return

    await query.answer()
    if query.message is None:
        return

    make_btn = lambda like: InlineKeyboardButton(
        text=str.capitalize(like),
        callback_data=SerialCbData(command=like, sub_command=callback_data.sub_command).pack(),
    )
    btn = make_btn("like" if callback_data.command == "unlike" else "unlike")

    if (
        isinstance(query.message.reply_markup, InlineKeyboardMarkup)
        and (kbd := deepcopy(query.message.reply_markup.inline_keyboard))
        and (
            like_btn := firstn(
                chain(*kbd),
                lambda b: b.callback_data
                and SerialCbData.unpack(b.callback_data).command in ["like", "unlike"],
            )
        )
    ):
        like_btn.callback_data = btn.callback_data
    else:
        kbd = [[btn]]

    await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=kbd))


async def like(self: InteractApp, message: Message, command: CommandObject):
    reply = message.reply_to_message
    if not reply:
        await message.reply(
            **Text("使用", CommandText(f"/{command.command}"), "时，您需要回复一条消息。").as_kwargs()
        )
        return

    err_msg = await like_core(self, int(reply.message_id))
    if err_msg is None:
        await message.reply("点赞成功")
    else:
        text = Text("点赞失败")
        if err_msg:
            text += Pre(err_msg)
        await message.reply(**text.as_kwargs())


command_like = BotCommand(command="like", description="点赞指定的说说")


def build_router(self: InteractApp) -> Router:
    router = Router(name="like")
    router.callback_query.register(
        self.btn_like,
        SerialCbData.filter(
            F.command.in_(["like", "unlike"]),
        ),
        SerialCbData.filter(F.sub_command.regexp(r"\d+")),
    )
    return router
