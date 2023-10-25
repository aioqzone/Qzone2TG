from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Final

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aioqzone.model import EmEntity, LikeData, PersudoCurkey

from ..storage.orm import FeedOrm
from .types import SerialCbData

MAX_CALLBACK_DATA: Final[int] = 64

if TYPE_CHECKING:
    from . import InteractApp


def queueevent_hook(app: InteractApp):
    from aioqzone_feed.type import FeedContent

    def _like_markup(feed: FeedContent) -> InlineKeyboardButton | None:
        if feed.unikey is None:
            return
        curkey = LikeData.persudo_curkey(feed.uin, feed.abstime)
        cbd = SerialCbData(command=("unlike" if feed.islike else "like"), sub_command=curkey)
        return InlineKeyboardButton(text="Unlike", callback_data=cbd.pack())

    def _emoji_markup(feed: FeedContent) -> InlineKeyboardButton | None:
        if not feed.entities:
            return
        eids = [e.eid for e in feed.entities if isinstance(e, EmEntity)]
        if not eids:
            return

        # NOTE: maybe a more compact encoding
        eids = [str(i) for i in set(eids)]
        cb = "emoji:"
        for i in eids:
            if len(cb) + len(i) <= MAX_CALLBACK_DATA:
                cb += i + ","
            else:
                break
        cb = cb.removesuffix(",")

        assert len(cb) <= MAX_CALLBACK_DATA
        return InlineKeyboardButton(text="Customize Emoji", callback_data=cb)

    async def reply_markup(feed: FeedContent) -> InlineKeyboardMarkup | None:
        row = [_emoji_markup(feed), _like_markup(feed)]
        row = list(filter(None, row))
        if row:
            return InlineKeyboardMarkup(inline_keyboard=[row])

    def qr_markup() -> InlineKeyboardMarkup | None:
        btnrefresh = InlineKeyboardButton(text="刷新", callback_data="qr:refresh")
        btncancel = InlineKeyboardButton(text="取消", callback_data="qr:cancel")
        return InlineKeyboardMarkup(inline_keyboard=[[btnrefresh, btncancel]])

    app.queue.reply_markup = reply_markup
    app._make_qr_markup = qr_markup


async def btn_like(self: InteractApp, query: CallbackQuery, callback_data: SerialCbData):
    data = callback_data.sub_command
    unlike = callback_data.command == "unlike"
    self.log.info(f"Like! query={data}")

    async def query_likedata(persudo_curkey: str) -> LikeData | None:
        p = PersudoCurkey.from_str(persudo_curkey)
        feed = await self.store.get_feed_orm(*FeedOrm.primkey(p))

        if feed is None or feed.unikey is None:
            await query.answer(
                text=f"未找到该消息，可能已超出 {self.conf.bot.storage.keepdays} 天。"
                if feed is None
                else "该说说不支持点赞。",
                show_alert=True,
            )
            if query.message:
                await query.message.edit_reply_markup(reply_markup=None)

            return

        return LikeData(
            unikey=str(feed.unikey),
            curkey=str(feed.curkey) or LikeData.persudo_curkey(feed.uin, feed.abstime),
            appid=feed.appid,
            typeid=feed.typeid,
            fid=feed.fid,
            abstime=feed.abstime,
        )

    async def like_trans(likedata: LikeData | None) -> bool:
        if likedata is None:
            return False

        try:
            succ = await self.qzone.internal_dolike_app(
                likedata.appid, likedata.unikey, likedata.curkey, not unlike
            )
        except:
            self.log.error("点赞失败", exc_info=True)
            return False

        if not succ:
            return False

        if query.message is None:
            return True

        if unlike:
            btn = InlineKeyboardButton(text="Like", callback_data="like:" + data)
        else:
            btn = InlineKeyboardButton(text="Unlike", callback_data="unlike:" + data)

        if isinstance(query.message.reply_markup, InlineKeyboardMarkup):
            kbd = query.message.reply_markup.inline_keyboard
            kbd = list(kbd[0])
            kbd[-1] = btn  # like button is the last
        else:
            kbd = [btn]

        await query.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[kbd])
        )
        return True

    succ = False
    with suppress():
        if likedata := await query_likedata(data):
            succ = await like_trans(likedata)

    if succ:
        await query.answer()
    else:
        await query.answer(text="点赞失败", show_alert=True)


async def btn_qr(self: InteractApp, query: CallbackQuery, callback_data: SerialCbData):
    match callback_data.sub_command:
        case "refresh":
            self._qrlogin.refresh_qr.set()
        case "cancel":
            self._qrlogin.cancel_qr.set()
        case _:
            self.log.warning(f"Unexpected qr button callback: {query.data}")
            if query.message:
                await query.message.delete()
            await query.answer("Unexpected qr button callback", show_alert=True)
            return
    await query.answer()


def build_router(self: InteractApp) -> Router:
    router = Router(name="inline_button")
    router.callback_query.register(self.btn_qr, SerialCbData.filter(F.command == "qr"))
    router.callback_query.register(
        self.btn_like, SerialCbData.filter(F.command.in_(["like", "unlike"]))
    )
    return router
