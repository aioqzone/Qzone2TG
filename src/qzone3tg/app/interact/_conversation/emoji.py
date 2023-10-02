from __future__ import annotations

import asyncio
import re
from enum import IntEnum, auto
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

import qzemoji as qe
from aiogram import (
    ForceReply,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from aiogram.ext import ContextTypes, ConversationHandler
from qzemoji.utils import build_html, wrap_plain_text

if TYPE_CHECKING:
    from qzone3tg.app.interact import InteractApp

TAG_RE = re.compile(r"\[em\]e(\d+)\[/em\]")


class EmCvState(IntEnum):
    CHOOSE_EID = auto()
    ASK_CUSTOM = auto()


async def _get_eid_bytes(self: InteractApp, eid: int) -> bytes | None:
    for ext in ("gif", "jpg", "png"):
        try:
            async with self.client.get(build_html(eid, ext=ext)) as r:
                return r.content
        except:
            pass


async def command_em(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when user sends ``/em eid [name]`` command.

    - If ``/em`` received, this method replys a help message and ends the conversation.
    - If ``/em eid`` received, this method replys the emoji photo and waits for the name.
    It will save the eid into `contenxt.user_data`. It will transmit the state graph to `ASK_CUSTOM`.
    - If ``/em eid name`` received, this method will save the name to database directly and notify
    success. It will transmit the state graph to `ConversationHandler.END`.

    """
    self.log.debug(context.args)
    assert update.message is not None

    match context.args:
        case ["export"]:
            await qe.export(Path("data/emoji.yml"))
            await update.message.reply_markdown_v2(r"已导出到`data/emoji\.yml`")
        case [eid] if str.isdigit(eid):
            content = await _get_eid_bytes(self, int(eid))
            if content is None:
                await update.message.reply_markdown_v2(f"未查询到`eid={eid}`")
                return ConversationHandler.END

            msg = await update.message.reply_photo(
                content,
                f"Input your customize text for e{eid}",
                reply_markup=ForceReply(selective=True, input_field_placeholder="/cancel"),
            )
            assert context.user_data is not None
            context.user_data["eid"] = eid
            context.user_data["to_delete"] = [msg.id, update.message.id]
            return EmCvState.ASK_CUSTOM
        case [eid, name] if str.isdigit(eid):
            await asyncio.gather(
                qe.set(int(eid), name),
                update.message.delete(),
                update.message.reply_markdown_v2(f"已将`{eid}`定义为{name}"),
            )
        case _:
            await update.message.reply_markdown_v2(
                dedent(
                    r"""用法:
                    1\. `/em <eid>`: 交互式自定义 eid 名称
                    2\. `/em <eid> <name>`: 直接指定 eid 的名称
                    3\. `/em export`: 导出所有 eid
                    """
                )
            )
    return ConversationHandler.END


async def btn_emoji(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This is the callback when user clicks the "Customize Emoji" button.

    This method will save the :class:`~telegram.Message` object into `context.user_data`.

    It will parse the message text for at most 9 unique emoji ids and arrange them into a button array.
    Then it will reply to the message with the :class:`ReplyKeyboardMarkup`, waiting for user's choice.

    This method will transmit the state graph to `CHOOSE_EID`.
    """
    query = update.callback_query
    assert context.user_data is not None
    assert query is not None
    assert query.data is not None

    if query.message is None:
        await query.answer("null query message", show_alert=True)
        return

    context.user_data["message"] = query.message
    text = query.message.text or query.message.caption or ""

    eids = query.data.removeprefix("emoji:").split(",")

    if len(eids) <= 9:
        max_eids = 9
        column = 3
    else:
        max_eids = 12
        column = 4

    eids = list(set(eids))[:max_eids]
    rows = [eids[i : i + column] for i in range(0, len(eids), column)]
    await query.message.reply_text(
        "Choose a emoji id",
        reply_markup=ReplyKeyboardMarkup(
            rows,
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="/cancel",
            selective=True,
            is_persistent=True,
        ),
    )
    return EmCvState.CHOOSE_EID


async def input_eid(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when user sends a emoji id to the bot. It should be triggered under the
    `CHOOSE_EID` state.

    This method will save the emoji id into `context.user_data`.

    This method will send the emoji photo to the user, asking for its customized name. If failed to get the
    emoji photo contents, the conversation will be terminated.

    This method will transmit the state graph to `ASK_CUSTOM`.
    """
    assert context.user_data is not None
    assert update.message is not None

    assert isinstance(update.message.text, str)
    try:
        eid = int(update.message.text)
    except ValueError:
        await update.message.reply_text(f"请输入数字（当前输入{update.message.text}）")
        return EmCvState.CHOOSE_EID

    content = await _get_eid_bytes(self, eid)
    if content is None:
        await update.message.reply_text(f"未查询到eid={eid}")
        return ConversationHandler.END

    msg = await update.message.reply_photo(
        build_html(eid),
        f"Input your customize text for e{eid}",
        reply_markup=ForceReply(selective=True, input_field_placeholder="/cancel"),
    )
    context.user_data["eid"] = eid
    context.user_data["to_delete"] = [msg.id]
    return EmCvState.ASK_CUSTOM


async def update_eid(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when the user replys a customized emoji name. It should be triggerd
    under the `ASK_CUSTOM` state.

    This method will load the emoji id, original message text, original message text attribute name from
    `context.user_data`.

    This method will save the customized name into database via `qzemoji.set`. It will replace the emoji ids
    in the original message text with the newly defined customized emoji name.
    It will delete all messages sent in this operation, then notify the user that the operation is success.
    It will clear the `context.user_data`.

    This method will transmit the state graph to `ConversationHandler.END`.
    """
    assert context.user_data is not None
    assert update.message is not None

    assert isinstance(update.message.text, str)

    eid: int = context.user_data["eid"]
    chat_id = update.message.chat_id
    name = update.message.text.strip()

    to_del: list[int] = context.user_data.get("to_delete", [])
    bot = update.get_bot()

    if "message" in context.user_data:
        message: Message = context.user_data["message"]
        text = message.text or message.caption or ""
        new_text = text.replace(f"[em]e{eid}[/em]", wrap_plain_text(name))

        reply_markup = message.reply_markup
        if reply_markup and TAG_RE.search(new_text) is None:
            # remove emoji inline button
            row = reply_markup.inline_keyboard[0]
            row = row[1:]
            reply_markup = InlineKeyboardMarkup([row]) if row else None

        if message.text:
            await message.edit_text(new_text, reply_markup=reply_markup)
        elif message.caption:
            await bot.edit_message_caption(new_text, reply_markup=reply_markup)

    await asyncio.gather(
        qe.set(eid, name),
        update.message.reply_markdown_v2(f"You have set `{eid}` to {name}"),
        *(bot.delete_message(chat_id, i) for i in to_del),
        bot.delete_message(chat_id, update.message.id),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_custom(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when user sends ``/cancel`` to cancel the customization process.

    It will clear `context.user_data` and notify the user that the process is canceled.

    This method will transmit the state graph to `ConversationHandler.END`.
    """
    assert update.message is not None

    if context.user_data is not None:
        context.user_data.clear()
    await update.message.reply_text(
        "Customize emoji canceled.", reply_markup=ReplyKeyboardRemove(selective=True)
    )
    return ConversationHandler.END
