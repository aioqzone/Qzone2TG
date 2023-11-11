from __future__ import annotations

import typing as t

from aiogram.filters.command import CommandObject
from aiogram.types import BotCommand, Message
from aiogram.utils.formatting import BotCommand as CommandText
from aiogram.utils.formatting import Text, as_key_value, as_marked_section, as_numbered_section

if t.TYPE_CHECKING:
    from . import InteractApp

COMMENT_CMD_HELP = as_marked_section(
    "帮助：",
    as_key_value(CommandText("/comment list"), "查看当前引用说说的评论"),
    as_key_value(CommandText("/comment add <content>"), "回复引用的说说"),
    as_key_value(CommandText("/comment add private <content>"), "私密回复引用的说说"),
)


async def comment(self: InteractApp, message: Message, command: CommandObject):
    reply = message.reply_to_message
    if not reply:
        await message.reply(
            **Text("使用", CommandText(f"/{command.command}"), "时，您需要回复一条消息。").as_kwargs()
        )
        return

    async def query_fid(mid: int):
        feed = await self.Mid2Feed(reply.message_id)
        if not feed:
            await message.reply(f"未找到该消息，可能已超出 {self.conf.bot.storage.keepdays} 天。")
            return
        return feed

    if not command.args:
        await message.reply(**COMMENT_CMD_HELP.as_kwargs())
        return

    match command.args.split():
        case ["add", content]:
            if orm := await query_fid(reply.message_id):
                await self.qzone.add_comment(orm.uin, orm.fid, orm.appid, content)
        case ["add", "private", content]:
            if orm := await query_fid(reply.message_id):
                await self.qzone.add_comment(orm.uin, orm.fid, orm.appid, content, private=True)
        case ["list"]:
            if orm := await query_fid(reply.message_id):
                detail = await self.qzone.shuoshuo(orm.fid, orm.uin, orm.appid)
                comments = sorted(detail.comment.comments, key=lambda comment: comment.commentid)
                text = as_numbered_section(
                    "评论：",
                    *(
                        as_key_value(comment.user.nickname, comment.content)
                        for comment in comments
                    ),
                )
                await message.reply(**text.as_kwargs())
        case _:
            await message.reply(**COMMENT_CMD_HELP.as_kwargs())


command_comment = BotCommand(command="comment", description="查看评论、发评论")
