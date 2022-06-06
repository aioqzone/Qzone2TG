"""This module defines an app that interact with user using /command and inline markup buttons."""
import asyncio

import qzemoji as qe
from aiohttp import ClientSession as Session
from aioqzone.interface.hook import LoginMethod
from aioqzone.type.internal import LikeData, PersudoCurkey
from aioqzone_feed.type import FeedContent
from telegram import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    Dispatcher,
    Filters,
    MessageFilter,
)

from qzone3tg.settings import PollingConf, Settings

from .base import BaseApp
from .storage import AsyncEngine
from .storage.orm import FeedOrm


class LockFilter(MessageFilter):
    def __init__(self) -> None:
        super().__init__()
        self.locked = False

    def filter(self, message):
        return not self.locked

    def acquire(self, task: asyncio.Task):
        self.locked = True
        task.add_done_callback(lambda _: setattr(self, "locked", False))


class InteractApp(BaseApp):
    commands = {
        "start": "刷新",
        "status": "获取运行状态",
        "relogin": "强制重新登陆",
        "em": "自定义表情代码，如 /em 400343 🐷；导出自定义表情，/em export",
        "like": "点赞指定的说说",
        "help": "帮助",
    }

    def __init__(self, sess: Session, store: AsyncEngine, conf: Settings) -> None:
        super().__init__(sess, store, conf)
        self.fetch_lock = LockFilter()

    # --------------------------------
    #            hook init
    # --------------------------------
    @property
    def _tasker_hook_cls(self):
        class interact_tasker_hook(super()._tasker_hook_cls):
            def _like_markup(self, feed: FeedContent) -> InlineKeyboardMarkup | None:
                if feed.unikey is None:
                    return
                curkey = LikeData.persudo_curkey(feed.uin, feed.abstime)
                if feed.islike:
                    likebtn = InlineKeyboardButton("Unlike", callback_data="like:-" + curkey)
                else:
                    likebtn = InlineKeyboardButton("Like", callback_data="like:" + curkey)
                return InlineKeyboardMarkup([[likebtn]])

            async def reply_markup(self, feed: FeedContent):
                markup = []
                if isinstance(feed.forward, FeedContent):
                    markup.append(self._like_markup(feed.forward))
                else:
                    markup.append(None)
                markup.append(self._like_markup(feed))
                return markup

        return interact_tasker_hook

    @property
    def _login_hook_cls(self):
        cls = super()._login_hook_cls

        class interact_qr_hook(cls._get_base(LoginMethod.qr)):
            def qr_markup(self):
                btnrefresh = InlineKeyboardButton("刷新", callback_data="qr:refresh")
                btncancel = InlineKeyboardButton("取消", callback_data="qr:cancel")
                return InlineKeyboardMarkup([[btnrefresh, btncancel]])

        class interact_login_hook(cls):
            @classmethod
            def _get_base(cls, meth: LoginMethod):
                if meth == LoginMethod.qr:
                    return interact_qr_hook
                return super()._get_base(meth)

        return interact_login_hook

    @property
    def _feed_hook_cls(self):
        cls = super()._feed_hook_cls

        class interact_feed_hook(cls):
            async def HeartbeatRefresh(_self, num: int):
                if self.fetch_lock.locked:
                    self.log.warning("Heartbeat refresh skipped since fetch is running.")
                    return
                self.fetch_lock.acquire(await super().HeartbeatRefresh(num))  # type: ignore

        return interact_feed_hook

    def set_commands(self):
        # build chat filters
        ca_id = [self.conf.bot.admin]
        ca_un = []
        CA = Filters.chat(chat_id=ca_id, username=ca_un)

        dispatcher: Dispatcher = self.updater.dispatcher
        has_fetch = ["start", "refresh"]
        for command in self.commands:
            dispatcher.add_handler(
                CommandHandler(
                    command,
                    getattr(self, command, self.help),
                    filters=(CA | self.fetch_lock) if command in has_fetch else CA,
                )
            )
        dispatcher.add_handler(CallbackQueryHandler(self.btn_dispatch))

        try:
            self.updater.bot.set_my_commands(
                [BotCommand(command=k, description=v) for k, v in self.commands.items()]
            )
        except:
            self.log.error("Error in setting commands", exc_info=True)

    async def run(self):
        if isinstance(self.conf.bot.init_args, PollingConf):
            self.updater.start_polling(**self.conf.bot.init_args.dict())
        else:
            token = self.conf.bot.token
            assert token
            kw = self.conf.bot.init_args.dict(exclude={"destination", "cert", "key"})
            safe_asposix = lambda p: p and p.as_posix()
            self.updater.start_webhook(
                url_path=token.get_secret_value(),
                webhook_url=self.conf.bot.init_args.webhook_url(token).get_secret_value(),
                cert=safe_asposix(self.conf.bot.init_args.cert),
                key=safe_asposix(self.conf.bot.init_args.key),
                **kw,
            )
        self.set_commands()
        return await super().run()

    # --------------------------------
    #            command
    # --------------------------------
    def start(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        self.log.info("Start! chat=%d", chat.id)
        task = self.add_hook_ref("command", self.fetch(chat.id))
        self.fetch_lock.acquire(task)

    def help(self, update: Update, context: CallbackContext):
        from .. import DOCUMENT

        chat = update.effective_chat
        assert chat
        helpm = "\n".join(f"/{k} - {v}" for k, v in self.commands.items())
        helpm += "\n\n讨论群：@qzone2tg_discuss"
        helpm += f"\n文档：{DOCUMENT}/usage.html"
        task = self.add_hook_ref("command", self.bot.send_message(chat.id, helpm))

    def status(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        if context.args and len(context.args) == 1 and context.args[0].lower() == "debug":
            coro = super().status(chat.id, debug=True)
        else:
            coro = super().status(chat.id)
        task = self.add_hook_ref("command", coro)

    def relogin(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        task = self.add_hook_ref("command", self.qzone.api.login.new_cookie())

    def em(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        echo = lambda m: self.add_hook_ref("command", self.bot.send_message(chat.id, m))

        if not context.args or len(context.args) not in [1, 2]:
            # fmt: off
            echo("错误的输入格式。示例：\n" \
                "/em 400343，展示图片\n" \
                "/em 400343 🐷，自定义表情文字\n" \
                "/em export，导出自定义表情")
            # fmt: on
            return

        if len(context.args) == 1:
            # /em <eid> or /em export
            try:
                eid = int(context.args[0])
            except ValueError:
                if context.args[0] == "export":
                    task = self.add_hook_ref("command", qe.export())
                    task.add_done_callback(lambda t: echo(f"已导出到{t.result().as_posix()}."))
                else:
                    echo("错误的输入格式。示例：\n/em 400343，展示图片\n/em export，导出自定义表情")
                return

            async def show_eid(eid: int):
                msg = f'示例： /em {eid} {(await qe.query(eid)) or "😅"}'
                for ext in ["gif", "png", "jpg"]:
                    async with self.sess.get(qe.utils.build_html(eid, ext=ext)) as r:
                        if r.status != 200:
                            continue
                        b = await r.content.read()
                        self.add_hook_ref("command", self.bot.send_photo(chat.id, b, msg))
                    return
                else:
                    echo(f"eid={eid}不存在，请检查输入")

            self.add_hook_ref("command", show_eid(eid))
            return

        eid, text = context.args
        eid = int(eid)
        echo(f"Customize emoji text: {eid}->{text}")
        self.add_hook_ref("storage", qe.set(eid, text))

    async def like(self, update: Update, context: CallbackContext):
        msg = update.effective_message
        assert msg
        reply = msg.reply_to_message
        if not reply:
            msg.reply_text("使用 /like 时，您需要回复一条消息。")
            return

        feed = await self.hook_store.Mid2Feed(reply.message_id)
        if not feed:
            msg.reply_text(f"未找到该消息，可能已超出 {self.conf.bot.storage.keepdays} 天。")
            return

        if feed.unikey is None:
            msg.reply_text("该说说不支持点赞。")
            return

        likedata = LikeData(
            unikey=str(feed.unikey),
            curkey=str(feed.curkey) or LikeData.persudo_curkey(feed.uin, feed.abstime),
            appid=feed.appid,
            typeid=feed.typeid,
            fid=feed.fid,
            abstime=feed.abstime,
        )
        task = self.add_hook_ref("button", self.qzone.like_app(likedata, True))
        task.add_done_callback(lambda t: check_succ(t))

        def check_succ(task: asyncio.Task[bool]):
            try:
                assert task.result()
            except:
                msg.reply_text("点赞失败")
            else:
                msg.reply_text("点赞成功")

    # --------------------------------
    #              query
    # --------------------------------
    def btn_dispatch(self, update: Update, context: CallbackContext):
        query: CallbackQuery = update.callback_query
        data: str = query.data
        prefix, data = data.split(":", maxsplit=1)
        switch = {"like": self.btn_like, "qr": self.btn_qr}
        switch[prefix](query)

    def btn_like(self, query: CallbackQuery):
        self.log.info(f"Like! query={query.data}")
        _, data = str.split(query.data, ":", maxsplit=1)
        if unlike := data.startswith("-"):
            data = data.removeprefix("-")

        async def query_likedata(persudo_curkey: str) -> LikeData | None:
            p = PersudoCurkey.from_str(persudo_curkey)
            r = await self.store.get(FeedOrm.uin == p.uin, FeedOrm.abstime == p.abstime)
            if r is None:
                return None
            feed, _ = r
            if feed.unikey is None:
                return
            return LikeData(
                unikey=str(feed.unikey),
                curkey=str(feed.curkey) or LikeData.persudo_curkey(feed.uin, feed.abstime),
                appid=feed.appid,
                typeid=feed.typeid,
                fid=feed.fid,
                abstime=feed.abstime,
            )

        def like_trans(likedata: LikeData | None):
            if likedata is None:
                try:
                    query.answer(text=f"记录已丢失。可能是记录已被清理，或此消息本应发送失败。")
                except:
                    pass
                try:
                    query.edit_message_reply_markup()
                except:
                    self.log.error("Failed to change button", exc_info=True)
                return

            task = self.add_hook_ref("button", self.qzone.like_app(likedata, not unlike))
            task.add_done_callback(check_succ)

        def check_succ(succ: asyncio.Task[bool]):
            try:
                assert succ.result()
            except:
                query.answer(text="点赞失败")
                return

            if unlike:
                btn = InlineKeyboardButton("Like", callback_data="like:" + data)
            else:
                btn = InlineKeyboardButton("Unlike", callback_data="like:-" + data)
            try:
                query.edit_message_reply_markup(InlineKeyboardMarkup([[btn]]))
            except:
                self.log.error("Failed to change button", exc_info=True)

        task = self.add_hook_ref("storage", query_likedata(data))
        task.add_done_callback(lambda t: like_trans(t.result()))

    def btn_qr(self, query: CallbackQuery):
        self.log.info(f"QR! query={query.data}")
        _, command = str.split(query.data, ":", maxsplit=1)
        switch = {"refresh": self.hook_qr.resend, "cancel": self.hook_qr.cancel}
        f = switch[command]
        if f:
            task = self.add_hook_ref("button", f())
            if command == "cancel":
                task.add_done_callback(
                    lambda t: query.delete_message() and setattr(self.hook_qr, "qr_msg", None)
                )
        else:
            query.delete_message()
