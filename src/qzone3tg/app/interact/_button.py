from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aioqzone.model import EmEntity, LikeData

from .types import MAX_CALLBACK_DATA, SerialCbData

if TYPE_CHECKING:
    from . import InteractApp


def add_button_impls(self: InteractApp):
    from aioqzone_feed.type import FeedContent

    @self.queue.inline_buttons.add_impl
    def _comment_markup(feed: FeedContent) -> InlineKeyboardButton | None:
        cbd = SerialCbData(command="comment", sub_command=feed.fid)
        return InlineKeyboardButton(text="Comment", callback_data=cbd.pack())

    @self.queue.inline_buttons.add_impl
    def _like_markup(feed: FeedContent) -> InlineKeyboardButton | None:
        if feed.unikey is None:
            return
        curkey = LikeData.persudo_curkey(feed.uin, feed.abstime)
        cbd = SerialCbData(command=("unlike" if feed.islike else "like"), sub_command=curkey)
        return InlineKeyboardButton(text=cbd.command.capitalize(), callback_data=cbd.pack())

    @self.queue.inline_buttons.add_impl
    def _emoji_markup(feed: FeedContent) -> InlineKeyboardButton | None:
        if not feed.entities:
            return
        eids = [e.eid for e in feed.entities if isinstance(e, EmEntity)]
        if not eids:
            return

        # NOTE: maybe a more compact encoding
        eids = [str(i) for i in set(eids)]
        cb = ""
        for i in eids:
            if len(cb) + len(i) <= MAX_CALLBACK_DATA:
                cb += i + ","
            else:
                break
        cb = cb.removesuffix(",")

        assert len(cb) <= MAX_CALLBACK_DATA
        return InlineKeyboardButton(
            text="Customize Emoji",
            callback_data=SerialCbData(command="emoji", sub_command=cb).pack(),
        )

    def qr_markup() -> InlineKeyboardMarkup | None:
        cbd = lambda sub_command: SerialCbData(command="qr", sub_command=sub_command).pack()
        btnrefresh = InlineKeyboardButton(text="刷新", callback_data=cbd("refresh"))
        btncancel = InlineKeyboardButton(text="取消", callback_data=cbd("cancel"))
        return InlineKeyboardMarkup(inline_keyboard=[[btnrefresh, btncancel]])

    self._make_qr_markup = qr_markup


async def btn_qr(self: InteractApp, query: CallbackQuery, callback_data: SerialCbData):
    match callback_data.sub_command:
        case "refresh":
            self.login.qr.refresh_qr.set()
        case "cancel":
            self.login.qr.cancel_qr.set()
        case _:
            self.log.warning(f"Unexpected qr button callback: {query.data}")
            if query.message:
                await query.message.delete()
            await query.answer("Unexpected qr button callback", show_alert=True)
            return
    await query.answer()


def build_router(self: InteractApp) -> Router:
    router = Router(name="inline_button")
    router.callback_query.register(
        self.btn_qr,
        SerialCbData.filter(F.command == "qr"),
        SerialCbData.filter(F.sub_command.in_({"refresh", "cancel"})),
    )
    return router
