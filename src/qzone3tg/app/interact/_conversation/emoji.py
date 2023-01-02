from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import qzemoji as qe
from aioqzone_feed.api.emoji import TAG_RE
from qzemoji.utils import build_html
from telegram import ForceReply, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler

if TYPE_CHECKING:
    from qzone3tg.app.interact import InteractApp

CHOOSE_EID, ASK_CUSTOM = range(2)


async def btn_emoji(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This is the callback when user clicks the "Customize Emoji" button.

    This method will save message text, message text attribute name, message id into `context.user_data`.

    It will parse the message text for at most 9 unique emoji ids and arrange them into a button array.
    Then it will reply to the message with the `ReplyKeyboardMarkup`, waiting for user's choice.

    This method will transmit the state graph to `CHOOSE_EID`.
    """
    query = update.callback_query
    assert context.user_data
    if query.message.text:
        context.user_data["tattr"] = "text"
        text = query.message.text
    elif query.message.caption:
        context.user_data["tattr"] = "caption"
        text = query.message.caption
    else:
        return ConversationHandler.END

    eids = TAG_RE.findall(text)
    if not eids:
        return ConversationHandler.END

    eids = list(set(eids))[:9]
    rows = [eids[i : i + 3] for i in range(0, len(eids), 3)]
    await query.message.reply_text(
        "Choose a emoji id",
        reply_markup=ReplyKeyboardMarkup(
            rows, one_time_keyboard=True, input_field_placeholder="/cancel", selective=True
        ),
    )
    context.user_data["mid"] = query.message.id
    context.user_data["text"] = text
    return CHOOSE_EID


async def input_eid(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when user sends a emoji id to the bot. It should be triggered under the
    `CHOOSE_EID` state.

    This method will save the emoji id into `context.user_data`.

    This method will send the emoji photo to the user, asking for its customized name.

    This method will transmit the state graph to `ASK_CUSTOM`.
    """
    eid = int(update.message.text)
    msg = await update.message.reply_photo(
        build_html(eid),
        f"Input your customize text for e{eid}",
        reply_markup=ForceReply(selective=True, input_field_placeholder="/cancel"),
    )
    assert context.user_data
    context.user_data["eid"] = eid
    context.user_data["to_delete"] = [msg.id]
    return ASK_CUSTOM


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
    assert context.user_data

    eid: int = context.user_data["eid"]
    chat_id = update.message.chat_id
    message_id: int = context.user_data["mid"]

    text: str = context.user_data["text"]
    name = update.message.text.strip()
    new_text = text.replace(
        f"[em]e{eid}[/em]",
        name if re.fullmatch(r"[^\u0000-\uFFFF]*", name) else f"[/{name}]",
    )

    to_del: list[int] = context.user_data["to_delete"]

    bot = update.get_bot()
    f = dict(
        text=lambda t: bot.edit_message_text(t, chat_id, message_id),
        caption=lambda t: bot.edit_message_caption(chat_id, message_id, caption=t),
    )[context.user_data["tattr"]]

    await asyncio.gather(
        qe.set(eid, name),
        update.message.reply_text(f"You have set {eid} to {name}."),
        f(new_text),
        bot.delete_message(chat_id, to_del[0]),
        bot.delete_message(chat_id, update.message.id),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_custom(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when user sends ``/cancel`` to cancel the customization process.

    It will clear `context.user_data` and notify the user that the process is canceled.

    This method will transmit the state graph to `ConversationHandler.END`.
    """
    assert context.user_data
    context.user_data.clear()
    await update.message.reply_text(
        "Customize emoji canceled.", reply_markup=ReplyKeyboardRemove(selective=True)
    )
    return ConversationHandler.END
