from __future__ import annotations

from typing import TYPE_CHECKING

from aioqzone.event import QREvent
from aioqzone.type.entity import EmEntity
from aioqzone.type.internal import LikeData, PersudoCurkey
from qqqr.event import sub_of
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ...bot.queue import QueueEvent
from ..storage.orm import FeedOrm

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from . import InteractApp


@sub_of(QueueEvent)
def queueevent_hook(_self: InteractApp, base: type[QueueEvent]):
    from aioqzone_feed.type import FeedContent
    from telegram.constants import InlineKeyboardButtonLimit

    from qzone3tg.type import FeedPair

    class interactapp_queueevent(base):
        def _like_markup(self, feed: FeedContent) -> InlineKeyboardButton | None:
            if feed.unikey is None:
                return
            curkey = LikeData.persudo_curkey(feed.uin, feed.abstime)
            if feed.islike:
                return InlineKeyboardButton("Unlike", callback_data="like:-" + curkey)
            else:
                return InlineKeyboardButton("Like", callback_data="like:" + curkey)

        def _emoji_markup(self, feed: FeedContent) -> InlineKeyboardButton | None:
            if not feed.entities:
                return
            eids = [e.eid for e in feed.entities if isinstance(e, EmEntity)]
            if not eids:
                return

            # NOTE: maybe a more compact encoding
            eids = [str(i) for i in set(eids)]
            cb = "emoji:"
            for i in eids:
                if len(cb) + len(i) <= InlineKeyboardButtonLimit.MAX_CALLBACK_DATA:
                    cb += i + ","
                else:
                    break
            cb = cb.removesuffix(",")

            assert len(cb) <= InlineKeyboardButtonLimit.MAX_CALLBACK_DATA
            return InlineKeyboardButton("Customize Emoji", callback_data=cb)

        def _reply_markup_one_feed(self, feed: FeedContent) -> InlineKeyboardMarkup | None:
            row = [self._emoji_markup(feed), self._like_markup(feed)]
            row = list(filter(None, row))
            if row:
                return InlineKeyboardMarkup([row])

        async def reply_markup(self, feed: FeedContent, need_forward: bool):
            pair = FeedPair(None, None)  # type: FeedPair[InlineKeyboardMarkup | None]
            if need_forward and isinstance(feed.forward, FeedContent):
                pair.forward = self._reply_markup_one_feed(feed.forward)
            pair.feed = self._reply_markup_one_feed(feed)
            return pair

    return interactapp_queueevent


@sub_of(QREvent)
def qrevent_hook(_self: InteractApp, base: type[QREvent]):
    class interactapp_qrevent(base):
        def qr_markup(self):
            btnrefresh = InlineKeyboardButton("刷新", callback_data="qr:refresh")
            btncancel = InlineKeyboardButton("取消", callback_data="qr:cancel")
            return InlineKeyboardMarkup([[btnrefresh, btncancel]])

    return interactapp_qrevent


async def btn_like(self: InteractApp, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    assert query
    if query.data is None or ":" not in query.data:
        self.log.warning(f"wrong callback data from update {update.update_id}")
        self.log.debug(query)
        await query.answer(f"invalid query data: {query.data}", show_alert=True)
        return

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
        assert query
        assert query.message

        with self.loginman.disable_suppress():
            try:
                succ = await self.qzone.internal_dolike_app(
                    likedata.appid, likedata.unikey, likedata.curkey, not unlike
                )
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
    assert query
    if query.data is None:
        await query.answer("null query data", show_alert=True)
        self.log.debug(query)
        return

    self.log.info(f"QR! query={query.data}")

    match query.data:
        case "qr:refresh":
            self[QREvent].refresh_flag.set()
        case "qr:cancel":
            self[QREvent].cancel_flag.set()
        case _:
            self.log.warning(f"Unexpected qr button callback: {query.data}")
            await query.delete_message()
            await query.answer("Unexpected qr button callback", show_alert=True)
            return
    await query.answer()
