from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

import qzemoji as qe
from aiogram import F, Router
from aiogram import filters as filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    ForceReply,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.formatting import BotCommand as CommandText
from aiogram.utils.formatting import Pre, Text, as_key_value, as_marked_section
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from qzemoji.utils import build_html

if TYPE_CHECKING:
    from qzone3tg.app.interact import InteractApp, SerialCbData

TAG_RE = re.compile(r"\[em\]e(\d+)\[/em\]")
EM_HELP = as_marked_section(
    "用法：",
    as_key_value(CommandText("/em <eid>"), "交互式自定义 eid 名称"),
    as_key_value(CommandText("/em <eid> <name>"), "直接指定 eid 的名称"),
    as_key_value(CommandText("/em export"), "导出所有 eid"),
)


class EmForm(StatesGroup):
    GET_EID = State()
    GET_TEXT = State()


async def _get_eid_bytes(self: InteractApp, eid: int) -> BufferedInputFile | None:
    for ext in ("gif", "jpg", "png"):
        try:
            async with self.client.get(build_html(eid, ext=ext)) as r:
                return BufferedInputFile(await r.content.read(), f"e{eid}.{ext}")
        except:
            pass


async def em(self: InteractApp, message: Message, state: FSMContext) -> None:
    """This method is the callback when user sends ``/em eid [name]`` command.

    - If ``/em`` received, this method replys a help message and ends the conversation.
    - If ``/em eid`` received, this method replys the emoji photo and waits for the name.
    It will save the eid into `contenxt.user_data`. It will transmit the state graph to `ASK_CUSTOM`.
    - If ``/em eid name`` received, this method will save the name to database directly and notify
    success. It will transmit the state graph to `ConversationHandler.END`.

    """
    self.log.debug(message.text)
    assert message.text is not None

    match message.text.split()[1:]:
        case "export":
            await qe.export(Path("data/emoji.yml"))
            await message.reply(**Text("已导出到", Pre("data/emoji.yml")).as_kwargs())
        case [eid] if str.isdigit(eid):
            file = await _get_eid_bytes(self, int(eid))
            if file is None:
                await message.reply(**Text("未查询到", Pre("eid=", eid)).as_kwargs())
                return await state.clear()

            await message.reply_photo(
                file,
                **Text("输入", Pre("e", eid), "的自定义文本").as_kwargs(text_key="caption"),
                reply_markup=ForceReply(selective=True, input_field_placeholder="/cancel"),
            )
            await state.update_data(eid=int(eid))
            return await state.set_state(EmForm.GET_TEXT)
        case [eid, name] if str.isdigit(eid):
            await asyncio.wait(
                [
                    asyncio.ensure_future(i)
                    for i in (
                        qe.set(int(eid), name),
                        message.delete(),
                        message.reply(**Text("已将", Pre(eid), "定义为", name).as_kwargs()),
                    )
                ],
            )
        case _:
            await message.reply(**EM_HELP.as_kwargs())

    await state.clear()


command_em = BotCommand(command="em", description="管理自定义表情")


async def btn_emoji(query: CallbackQuery, callback_data: SerialCbData, state: FSMContext):
    """This is the callback when user clicks the "Customize Emoji" button.

    This method will save the :class:`~telegram.Message` object into `context.user_data`.

    It will parse the message text for at most 9 unique emoji ids and arrange them into a button array.
    Then it will reply to the message with the :class:`ReplyKeyboardMarkup`, waiting for user's choice.

    This method will transmit the state graph to `CHOOSE_EID`.
    """
    if query.message is None:
        await query.answer("null query message", show_alert=True)
        return

    eids = callback_data.sub_command.split(",")

    if len(eids) <= 9:
        max_eids = 9
        column = 3
    else:
        max_eids = 12
        column = 4

    eids = list(set(eids))[:max_eids]
    builder = ReplyKeyboardBuilder()
    for eid in eids[:max_eids]:
        builder.button(text=eid)
    builder.adjust(column)

    await query.message.reply(
        "选择或者输入一个 eid",
        reply_markup=builder.as_markup(
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="/cancel",
            selective=True,
            is_persistent=True,
        ),
    )
    await state.set_state(EmForm.GET_EID)


async def input_eid(self: InteractApp, message: Message, state: FSMContext):
    """This method is the callback when user sends a emoji id to the bot. It should be triggered under the
    `CHOOSE_EID` state.

    This method will save the emoji id into `context.user_data`.

    This method will send the emoji photo to the user, asking for its customized name. If failed to get the
    emoji photo contents, the conversation will be terminated.

    This method will transmit the state graph to `ASK_CUSTOM`.
    """
    assert isinstance(message.text, str)

    try:
        eid = int(message.text.strip())
    except ValueError:
        await message.reply(f"请输入数字（当前输入{message.text}）")
        return

    file = await _get_eid_bytes(self, eid)
    if file is None:
        await message.reply(**Text("未查询到", Pre("eid=", eid)).as_kwargs())
        return await state.clear()

    await message.reply_photo(
        file,
        **Text("输入", Pre("e", eid), "的自定义文本").as_kwargs(text_key="caption"),
        reply_markup=ForceReply(selective=True, input_field_placeholder="/cancel"),
    )
    await state.set_state(EmForm.GET_TEXT)


async def input_text(message: Message, state: FSMContext):
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
    assert isinstance(message.text, str)

    data = await state.get_data()
    eid = int(data["eid"])
    name = message.text.strip()

    await asyncio.wait(
        [
            asyncio.ensure_future(i)
            for i in (
                qe.set(eid, name),
                message.reply(**Text("已将", Pre(eid), "定义为", name).as_kwargs()),
                message.delete(),
            )
        ]
    )
    await state.clear()


async def cancel_custom(message: Message, state: FSMContext):
    """This method is the callback when user sends ``/cancel`` to cancel the customization process.

    It will clear `context.user_data` and notify the user that the process is canceled.

    This method will transmit the state graph to `ConversationHandler.END`.
    """
    if await state.get_state() is None:
        return
    await message.reply(
        "Customize emoji canceled.", reply_markup=ReplyKeyboardRemove(selective=True)
    )
    await state.clear()


def build_router(self: InteractApp) -> Router:
    from .. import SerialCbData

    router = Router(name="emoji")
    CA = F.from_user.id.in_({self.conf.bot.admin})

    # router.message.register(self.em, CA, filter.Command(command_em))
    router.callback_query.register(btn_emoji, SerialCbData.filter(F.command == "emoji"))
    router.message.register(self.input_eid, CA, F.text.regexp(r"^\s*\d+\s*$"), EmForm.GET_EID)
    router.message.register(input_text, CA, F.text, EmForm.GET_TEXT)
    router.message.register(cancel_custom, CA, filter.Command("cancel"))

    return router
