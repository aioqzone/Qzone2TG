from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import BotCommand, Message
from aiogram.utils.formatting import Bold
from aiogram.utils.formatting import BotCommand as CommandText
from aiogram.utils.formatting import Text, as_key_value, as_marked_section

if TYPE_CHECKING:
    from qzone3tg.app.interact import InteractApp

BLOCK_CMD_HELP = as_marked_section(
    Bold("帮助："),
    as_key_value(CommandText("/block"), "根据回复的消息查询 QQ，并将其加入黑名单"),
    as_key_value(CommandText("/block add <uin>"), "将 uin 加入黑名单"),
    as_key_value(CommandText("/block rm <uin>"), "从黑名单中移除 uin"),
    as_key_value(CommandText("/block list"), Text("列出所有", Bold("动态添加的"), "黑名单 QQ")),
)


async def block(self: InteractApp, message: Message):
    assert message.text
    match message.text.split()[1:]:
        case None | []:
            if message.reply_to_message is None:
                await message.reply(**BLOCK_CMD_HELP.as_kwargs())
                return
            # message id to uin
            feed = await self.Mid2Feed(message.reply_to_message.message_id)
            if feed is None:
                await message.reply("uin not found. Try `/block add <uin>` instead.")
                return
            await self.dyn_blockset.add(feed.uin)
            await message.reply(f"{feed.uin} 已加入黑名单")
        case ["rm", uin]:
            try:
                uin = int(uin)
            except:
                await message.reply(**BLOCK_CMD_HELP.as_kwargs())
                return
            if await self.dyn_blockset.delete(uin):
                await message.reply(f"{uin} 已从黑名单移除✅")
            else:
                await message.reply(f"{uin} 尚未被拉黑✅")
        case ["add", uin]:
            try:
                uin = int(uin)
            except:
                await message.reply(**BLOCK_CMD_HELP.as_kwargs())
                return

            await self.dyn_blockset.add(int(uin))
            await message.reply(f"{uin} 已加入黑名单")
        case ["list"]:
            uins = await self.dyn_blockset.all()
            if uins:
                await message.reply("\n".join(f"> {i}" for i in uins))
            else:
                await message.reply("黑名单中还没有用户✅")
        case _:
            await message.reply(**BLOCK_CMD_HELP.as_kwargs())


command_block = BotCommand(command="block", description="管理黑名单")
