from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from telegram import Update

    from qzone3tg.app.interact import InteractApp

BLOCK_CMD_HELP = """
`/block`: 根据回复的消息查询 QQ，并将其加入黑名单
`/block add <uin>`: 将 uin 加入黑名单
`/block rm <uin>`: 从黑名单中移除 uin
`/block list`: 列出所有 **动态添加的** 黑名单 QQ
"""


async def block(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    assert message
    echo = lambda text, **kw: message.reply_text(
        text=text, reply_to_message_id=message.id, parse_mode=ParseMode.MARKDOWN_V2, **kw
    )
    # NOTE: parse mode is MARKDOWN_V2, "_*[]()~`>#+-=|{}.!" must be escaped!!!

    match context.args:
        case None | []:
            if message.reply_to_message is None:
                await echo(BLOCK_CMD_HELP)
                return
            # message id to uin
            feed = await self.Mid2Feed(message.reply_to_message.id)
            if feed is None:
                await echo("uin not found. Try `/block add <uin>` instead.")
                return
            self.blockset.add(feed.uin)
            await self.dyn_blockset.add(feed.uin)
            await echo(f"{feed.uin} 已加入黑名单")
        case ["rm", uin]:
            try:
                uin = int(uin)
            except:
                await echo(BLOCK_CMD_HELP)
                return
            self.blockset.discard(uin)
            if await self.dyn_blockset.delete(uin):
                await echo(f"{uin} 已从黑名单移除✅")
            else:
                await echo(f"{uin} 尚未被拉黑✅")
        case ["add", uin]:
            try:
                uin = int(uin)
            except:
                await echo(BLOCK_CMD_HELP)
                return

            self.blockset.add(int(uin))
            await self.dyn_blockset.add(int(uin))
            await echo(f"{uin} 已加入黑名单")
        case ["list"]:
            uins = await self.dyn_blockset.all()
            if uins:
                await echo("\n".join(f"> {i}" for i in uins))
            else:
                await echo("黑名单中还没有用户✅")
        case _:
            await echo(BLOCK_CMD_HELP)
