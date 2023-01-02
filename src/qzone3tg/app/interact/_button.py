from __future__ import annotations

from typing import TYPE_CHECKING

from aioqzone.type.entity import AtEntity, TextEntity
from aioqzone.type.internal import LikeData, PersudoCurkey
from aioqzone_feed.api.emoji import TAG_RE
from aioqzone_feed.type import FeedContent
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..storage.orm import FeedOrm

if TYPE_CHECKING:
    from . import InteractApp


def hook_taskerevent(self: InteractApp, base):
    class interact_tasker_hook(base):
        def _like_markup(self, feed: FeedContent) -> InlineKeyboardButton | None:
            if feed.unikey is None:
                return
            curkey = LikeData.persudo_curkey(feed.uin, feed.abstime)
            if feed.islike:
                return InlineKeyboardButton("Unlike", callback_data="like:-" + curkey)
            else:
                return InlineKeyboardButton("Like", callback_data="like:" + curkey)

        def _emoji_markup(self, feed: FeedContent) -> InlineKeyboardButton | None:
            if feed.entities is None:
                return
            for e in feed.entities:
                match e:
                    case TextEntity(con=text) | AtEntity(nick=text):
                        if TAG_RE.search(text):
                            return InlineKeyboardButton("Customize Emoji", callback_data="emoji:")

        def _reply_markup_one_feed(self, feed: FeedContent) -> InlineKeyboardMarkup | None:
            row = []
            if m := self._emoji_markup(feed):
                row.append(m)
            if m := self._like_markup(feed):
                row.append(m)
            if row:
                return InlineKeyboardMarkup([row])

        async def reply_markup(self, feed: FeedContent):
            markup = []
            if isinstance(feed.forward, FeedContent):
                markup.append(self._reply_markup_one_feed(feed.forward))
            else:
                markup.append(None)
            markup.append(self._reply_markup_one_feed(feed))
            return markup

    return interact_tasker_hook


def hook_defaultqr(self: InteractApp, base):
    class has_markup(base):
        def qr_markup(self):
            btnrefresh = InlineKeyboardButton("刷新", callback_data="qr:refresh")
            btncancel = InlineKeyboardButton("取消", callback_data="qr:cancel")
            return InlineKeyboardMarkup([[btnrefresh, btncancel]])

    return has_markup


async def btn_like(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    self.log.info(f"Like! query={query.data}")
    _, data = str.split(query.data, ":", maxsplit=1)
    if unlike := data.startswith("-"):
        data = data.removeprefix("-")

    async def query_likedata(persudo_curkey: str) -> LikeData | None:
        p = PersudoCurkey.from_str(persudo_curkey)
        feed = await self.store.get_feed_orm(FeedOrm.uin == p.uin, FeedOrm.abstime == p.abstime)

        if feed is None or feed.unikey is None:
            for c in [
                query.answer(
                    text=f"未找到该消息，可能已超出 {self.conf.bot.storage.keepdays} 天。"
                    if feed is None
                    else "该说说不支持点赞。",
                    show_alert=True,
                ),
                query.edit_message_reply_markup(reply_markup=None),
            ]:
                try:
                    await c
                except:
                    pass
            return

        return LikeData(
            unikey=str(feed.unikey),
            curkey=str(feed.curkey) or LikeData.persudo_curkey(feed.uin, feed.abstime),
            appid=feed.appid,
            typeid=feed.typeid,
            fid=feed.fid,
            abstime=feed.abstime,
        )

    async def like_trans(likedata: LikeData):
        with self.loginman.disable_suppress():
            try:
                succ = await self.qzone.like_app(likedata, not unlike)
            except:
                self.log.error("点赞失败", exc_info=True)
                succ = False
        if not succ:
            await query.answer(text="点赞失败", show_alert=True)
            return

        if unlike:
            btn = InlineKeyboardButton("Like", callback_data="like:" + data)
        else:
            btn = InlineKeyboardButton("Unlike", callback_data="like:-" + data)
        if isinstance(query.message.reply_markup, InlineKeyboardMarkup):
            kbd = query.message.reply_markup.inline_keyboard
            kbd = list(kbd[0])
            kbd[-1] = btn
        else:
            kbd = [btn]

        try:
            await query.edit_message_reply_markup(InlineKeyboardMarkup([kbd]))
        except:
            pass

    likedata = await query_likedata(data)
    if likedata is None:
        return
    await like_trans(likedata)
    await query.answer()


async def btn_qr(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    self.log.info(f"QR! query={query.data}")

    match query.data:
        case "qr:refresh":
            self.hook_qr.refresh_flag.set()
        case "qr:cancel":
            self.hook_qr.cancel_flag.set()
            await query.delete_message()
            self.hook_qr.qr_msg = None
        case _:
            self.log.warning(f"Unexpected qr button callback: {query.data}")
            await query.delete_message()
            await query.answer("Unexpected qr button callback", show_alert=True)
            return
    await query.answer()