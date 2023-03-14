from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from qzone3tg.app.storage import StorageEvent

if TYPE_CHECKING:
    from telegram import Update

    from qzone3tg.app.interact import InteractApp

BLOCK_CMD_HELP = """
`/block`: Query uin from the message id to which the command replies, then add the uin into block set
`/block add <uin>`: Add the uin into block set
`/block rm <uin>`: Remove the uin from block set
`/block list`: List all **dynamically** blocked uins
"""


async def block(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    assert message
    echo = lambda text, **kw: message.reply_text(
        text=text, reply_to_message_id=message.id, parse_mode=ParseMode.MARKDOWN_V2, **kw
    )

    match context.args:
        case None | []:
            if message.reply_to_message is None:
                await echo(BLOCK_CMD_HELP)
                return
            # message id to uin
            feed = await self[StorageEvent].Mid2Feed(message.reply_to_message.id)
            if feed is None:
                await echo("uin not found. Try `/block add <uin>` instead.")
                return
            await self.blockset.add(feed.uin)
            await echo(f"{feed.uin} blocked.")
        case ["rm", uin]:
            try:
                uin = int(uin)
            except:
                await echo(BLOCK_CMD_HELP)
                return
            await self.blockset.delete(uin)
            await echo(f"{uin} unblocked.")
        case ["add", uin]:
            try:
                uin = int(uin)
            except:
                await echo(BLOCK_CMD_HELP)
                return
            await self.blockset.add(int(uin))
            await echo(f"{uin} blocked.")
        case ["list"]:
            uins = await self.blockset.all()
            await echo("\n".join(f"- {i}" for i in uins))
        case _:
            await echo(BLOCK_CMD_HELP)
