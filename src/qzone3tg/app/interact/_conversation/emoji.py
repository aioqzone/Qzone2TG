from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import cv2 as cv
import numpy as np
import qzemoji as qe
from aioqzone_feed.api.emoji import TAG_RE, wrap_plain_text
from qzemoji.utils import build_html
from telegram import ForceReply, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler

if TYPE_CHECKING:
    from qzone3tg.app.interact import InteractApp

CHOOSE_EID, ASK_CUSTOM = range(2)


async def _get_eid_bytes(self: InteractApp, eid: int) -> bytes | None:
    for ext in ("gif", "jpg", "png"):
        try:
            async with self.client.get(build_html(eid, ext=ext)) as r:
                return upsample(r.content, ext)
        except:
            pass


def upsample(content: bytes, ext: str, f=2.0) -> bytes:
    img = cv.imdecode(np.frombuffer(content, dtype=np.uint8), cv.IMREAD_UNCHANGED)
    img = cv.resize(img, None, fx=f, fy=f, interpolation=cv.INTER_CUBIC)  # type: ignore
    _, arr = cv.imencode(".jpg", img)
    return arr.tobytes()


async def command_em(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when user sends ``/em eid [name]`` command.

    - If ``/em`` received, this method replys a help message and ends the conversation.
    - If ``/em eid`` received, this method replys the emoji photo and waits for the name.
    It will save the eid into `contenxt.user_data`. It will transmit the state graph to `ASK_CUSTOM`.
    - If ``/em eid name`` received, this method will save the name to database directly and notify
    success. It will transmit the state graph to `ConversationHandler.END`.

    """
    self.log.debug(context.args)

    match context.args:
        case None | []:
            await update.message.reply_markdown_v2("usage: `/em eid [name]`")
            return ConversationHandler.END
        case ["export"]:
            await qe.export(Path("data/emoji.yml"))
            return ConversationHandler.END
        case [eid]:
            content = await _get_eid_bytes(self, int(eid))
            if content is None:
                await update.message.reply_text(f"未查询到eid={eid}")
                return ConversationHandler.END

            msg = await update.message.reply_photo(
                content,
                f"Input your customize text for e{eid}",
                reply_markup=ForceReply(selective=True, input_field_placeholder="/cancel"),
            )
            assert context.user_data is not None
            context.user_data["eid"] = eid
            context.user_data["to_delete"] = [msg.id, update.message.id]
            return ASK_CUSTOM
        case [eid, name]:
            await asyncio.gather(
                qe.set(int(eid), name),
                update.message.delete(),
                update.message.reply_markdown_v2(f"You have set `{eid}` to {name}"),
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

    context.user_data["message"] = query.message
    text = query.message.text or query.message.caption

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
    return CHOOSE_EID


async def input_eid(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This method is the callback when user sends a emoji id to the bot. It should be triggered under the
    `CHOOSE_EID` state.

    This method will save the emoji id into `context.user_data`.

    This method will send the emoji photo to the user, asking for its customized name. If failed to get the
    emoji photo contents, the conversation will be terminated.

    This method will transmit the state graph to `ASK_CUSTOM`.
    """
    assert context.user_data is not None
    eid = int(update.message.text)
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
    assert context.user_data is not None

    eid: int = context.user_data["eid"]
    chat_id = update.message.chat_id
    name = update.message.text.strip()

    to_del: list[int] = context.user_data.get("to_delete", [])
    bot = update.get_bot()

    if "message" in context.user_data:
        message: Message = context.user_data["message"]
        text = message.text or message.caption
        new_text = text.replace(f"[em]e{eid}[/em]", wrap_plain_text(name))

        if message.text:
            await message.edit_text(new_text)
        elif message.caption:
            await bot.edit_message_caption(new_text)

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
    assert context.user_data is not None
    context.user_data.clear()
    await update.message.reply_text(
        "Customize emoji canceled.", reply_markup=ReplyKeyboardRemove(selective=True)
    )
    return ConversationHandler.END
