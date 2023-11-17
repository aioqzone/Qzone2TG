from __future__ import annotations

import asyncio
import typing as t

from aiogram import F, Router
from aiogram.filters import or_f
from aiogram.filters.command import Command as CommandFilter
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, CallbackQuery, ForceReply, Message
from aiogram.utils.formatting import BotCommand as CommandText
from aiogram.utils.formatting import (
    Pre,
    Text,
    as_key_value,
    as_marked_section,
    as_numbered_section,
)

from ..types import SerialCbData

if t.TYPE_CHECKING:
    from .. import InteractApp

COMMENT_CMD_HELP = as_marked_section(
    "帮助：",
    as_key_value(CommandText("/comment list"), "查看当前引用说说的评论"),
    as_key_value(CommandText("/comment add <content>"), "回复引用的说说"),
    as_key_value(CommandText("/comment add private <content>"), "私密回复引用的说说"),
)


class CommentForm(StatesGroup):
    GET_COMMAND = State()
    GET_CONTENT = State()


async def btn_comment(query: CallbackQuery, callback_data: SerialCbData, state: FSMContext):
    if not query.message:
        await query.answer("query has no message", show_alert=True)
        return

    await asyncio.gather(
        state.update_data(fid=callback_data.sub_command, query_message=query.message),
        state.set_state(CommentForm.GET_COMMAND),
        query.message.reply(
            **Text("输入命令：", Pre("list"), Pre("add"), Pre("add private")).as_kwargs(),
            reply_markup=ForceReply(selective=True, input_field_placeholder="/cancel"),
        ),
    )


async def input_content(self: InteractApp, message: Message, state: FSMContext):
    data = await state.get_data()
    feed_message = data["query_message"]
    await comment_core(self, feed_message, message, message.text, state)


async def cancel_custom(message: Message, state: FSMContext):
    if await state.get_state() is None:
        return
    await message.reply("Cancelled.", reply_markup=None)
    await state.clear()


async def comment_core(
    self: InteractApp,
    feed_message: Message,
    trigger_message: Message | None,
    command: str | None,
    state: FSMContext | None = None,
):
    if trigger_message is None:
        trigger_message = feed_message

    if not command:
        await trigger_message.reply(**COMMENT_CMD_HELP.as_kwargs())
        return

    async def query_fid(mid: int):
        feed = await self.Mid2Feed(mid)
        if not feed:
            await trigger_message.reply(f"未找到该消息，可能已超出 {self.conf.bot.storage.keepdays} 天。")
            return
        return feed

    match command.strip().split(maxsplit=1):
        case ["add", content]:
            if state:
                await state.clear()
            if orm := await query_fid(feed_message.message_id):
                private = False
                if content.startswith("private "):
                    private = True
                    content = content.removeprefix("private").lstrip()
                await self.qzone.add_comment(orm.uin, orm.fid, orm.appid, content, private=private)
                await trigger_message.reply("评论成功")
        case ["list"]:
            if state:
                await state.clear()
            if orm := await query_fid(feed_message.message_id):
                detail = await self.qzone.shuoshuo(orm.fid, orm.uin, orm.appid)
                comments = sorted(detail.comment.comments, key=lambda comment: comment.commentid)
                if not comments:
                    await trigger_message.reply(
                        **Text(
                            "尚无评论！使用", CommandText("/command add <content>"), "发表评论！"
                        ).as_kwargs()
                    )
                    return

                text = as_numbered_section(
                    "评论：",
                    *(
                        as_key_value(comment.user.nickname, comment.content)
                        for comment in comments
                    ),
                )
                await feed_message.reply(**text.as_kwargs())
        case _:
            await trigger_message.reply(**COMMENT_CMD_HELP.as_kwargs())


async def comment(self: InteractApp, message: Message, command: CommandObject):
    feed_message = message.reply_to_message
    if feed_message is None:
        if command.args:
            await message.reply(
                **Text("使用", CommandText(f"/{command.command}"), "时，您需要回复一条消息。").as_kwargs()
            )
        else:
            await message.reply(**COMMENT_CMD_HELP.as_kwargs())
        return

    await comment_core(self, feed_message, message, command.args)


command_comment = BotCommand(command="comment", description="查看评论、发评论")


def build_router(self: InteractApp):
    router = Router(name="comment")
    CA = F.from_user.id.in_({self.conf.bot.admin})
    cancel = CommandFilter("cancel")
    any_state = or_f(CommentForm.GET_COMMAND, CommentForm.GET_CONTENT)

    router.callback_query.register(btn_comment, SerialCbData.filter(F.command == "comment"))
    router.message.register(self.input_content, CA, CommentForm.GET_COMMAND, F.text, ~cancel)
    router.message.register(cancel_custom, CA, cancel, any_state)
    return router
