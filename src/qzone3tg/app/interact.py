"""This module defines an app that interact with user using /command and inline markup buttons."""
import asyncio
from typing import Type

import qzemoji as qe
from aioqzone.type.internal import LikeData, PersudoCurkey
from aioqzone_feed.type import FeedContent
from qqqr.utils.net import ClientAdapter
from telegram import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from qzone3tg.app.hook import DefaultUpHook
from qzone3tg.settings import PollingConf, Settings

from .base import BaseApp
from .storage import AsyncEngine
from .storage.orm import FeedOrm


class LockFilter(filters.MessageFilter):
    def __init__(self) -> None:
        super().__init__()
        self.locked = False

    def filter(self, message):
        return not self.locked

    def acquire(self, task: asyncio.Task):
        self.locked = True
        task.add_done_callback(lambda _: setattr(self, "locked", False))


class ReplyHandler(MessageHandler):
    def __init__(self, filters, callback, reply: Message):
        super().__init__(filters, callback)
        self.reply = reply

    def check_update(self, update: Update):
        if super().check_update(update) is False:
            return False
        msg = update.effective_message
        assert msg

        if msg.reply_to_message and msg.reply_to_message.message_id == self.reply.message_id:
            return
        return False


class InteractApp(BaseApp):
    commands = {
        "start": "刷新",
        "status": "获取运行状态",
        "relogin": "强制重新登陆",
        "em": "自定义表情代码，如 /em 400343 🐷；导出自定义表情，/em export",
        "like": "点赞指定的说说",
        "help": "帮助",
    }

    def __init__(self, client: ClientAdapter, store: AsyncEngine, conf: Settings) -> None:
        super().__init__(client, store, conf)
        self.fetch_lock = LockFilter()

    # --------------------------------
    #            hook init
    # --------------------------------
    def _sub_taskerevent(self, base):
        class interact_tasker_hook(base):
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

    def _sub_defaultqrhook(self, base):
        base = super()._sub_defaultqrhook(base)

        class has_markup(base):
            def qr_markup(self):
                btnrefresh = InlineKeyboardButton("刷新", callback_data="qr:refresh")
                btncancel = InlineKeyboardButton("取消", callback_data="qr:cancel")
                return InlineKeyboardMarkup([[btnrefresh, btncancel]])

        return has_markup

    def _sub_defaultuphook(self, base: Type[DefaultUpHook]):
        class get_reply(base):
            async def force_reply_answer(_self, msg) -> str | None:
                code = ""
                evt = asyncio.Event()

                def cb(update: Update, _):
                    nonlocal code
                    assert update.effective_message
                    code = update.effective_message.text.strip()
                    evt.set()

                handler = ReplyHandler(filters.Regex(r"^\s*\d{6}\s*$"), cb, msg)
                self.app.add_handler(handler)

                try:
                    await asyncio.wait_for(evt.wait(), timeout=_self.vtimeout)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    return
                else:
                    return code
                finally:
                    self.app.remove_handler(handler)

        return get_reply

    def _sub_defaultfeedhook(self, base):
        base = super()._sub_defaultfeedhook(base)

        class interact_feed_hook(base):
            async def HeartbeatRefresh(_self, num: int):
                if self.fetch_lock.locked:
                    self.log.warning("Heartbeat refresh skipped since fetch is running.")
                    return
                self.fetch_lock.acquire(await super().HeartbeatRefresh(num))  # type: ignore

            async def HeartbeatFailed(_self, exc: BaseException | None):
                await super().HeartbeatFailed(exc)
                await self.bot.send_message(
                    self.admin, "/relogin 重新登陆，/help 查看帮助", disable_notification=True
                )

        return interact_feed_hook

    async def set_commands(self):
        # build chat filters
        ca_id = [self.conf.bot.admin]
        ca_un = []
        CA = filters.Chat(chat_id=ca_id, username=ca_un)

        has_fetch = ["start", "refresh"]
        for command in self.commands:
            self.app.add_handler(
                CommandHandler(
                    command,
                    getattr(self, command, self.help),
                    filters=(CA | self.fetch_lock) if command in has_fetch else CA,
                    block=False,
                )
            )
        self.app.add_handler(CallbackQueryHandler(self.btn_dispatch, block=False))

        try:
            await self.extbot.set_my_commands(
                [BotCommand(command=k, description=v) for k, v in self.commands.items()]
            )
        except:
            self.log.error("Error in setting commands", exc_info=True)

    async def run(self):
        """
        :meth:`InteractApp.run` will start polling or webhook, run its own preparations,
        and call :meth:`BaseApp.run`.

        :return: None

        .. versionchanged:: webhook listens to ``0.0.0.0`` instead of ``127.0.0.1``
        """

        conf = self.conf.bot.init_args
        await self.app.initialize()
        updater = self.app.updater
        assert updater
        if isinstance(conf, PollingConf):
            await updater.start_polling(**conf.dict())
        else:
            token = self.conf.bot.token
            assert token
            kw = conf.dict(exclude={"destination", "cert", "key"})
            safe_asposix = lambda p: p and p.as_posix()
            await updater.start_webhook(
                listen="0.0.0.0",
                url_path=token.get_secret_value(),
                webhook_url=conf.webhook_url(token).get_secret_value(),
                cert=safe_asposix(conf.cert),
                key=safe_asposix(conf.key),
                **kw,
            )
        await self.set_commands()
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

    async def help(self, update: Update, context: CallbackContext):
        from .. import DOCUMENT

        chat = update.effective_chat
        assert chat
        helpm = "\n".join(f"/{k} - {v}" for k, v in self.commands.items())
        helpm += "\n\n官方频道：@qzone2tg"
        helpm += "\n讨论群：@qzone2tg_discuss"
        helpm += f"\n文档：{DOCUMENT}/usage.html"
        task = self.add_hook_ref("command", self.bot.send_message(chat.id, helpm))

    async def status(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        if context.args and len(context.args) == 1 and context.args[0].lower() == "debug":
            coro = super().status(chat.id, debug=True)
        else:
            coro = super().status(chat.id)
        task = self.add_hook_ref("command", coro)

    async def relogin(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        task = self.add_hook_ref("command", self.qzone.api.login.new_cookie())

    async def em(self, update: Update, context: CallbackContext):
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
                    async with await self.client.get(qe.utils.build_html(eid, ext=ext)) as r:
                        if r.status_code != 200:
                            continue
                        self.add_hook_ref("command", self.bot.send_photo(chat.id, r.content, msg))
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
            await msg.reply_text("使用 /like 时，您需要回复一条消息。")
            return

        async def query_likedata(mid: int):
            feed = await self.hook_store.Mid2Feed(reply.message_id)
            if not feed:
                await msg.reply_text(f"未找到该消息，可能已超出 {self.conf.bot.storage.keepdays} 天。")
                return

            if feed.unikey is None:
                await msg.reply_text("该说说不支持点赞。")
                return

            return LikeData(
                unikey=str(feed.unikey),
                curkey=str(feed.curkey) or LikeData.persudo_curkey(feed.uin, feed.abstime),
                appid=feed.appid,
                typeid=feed.typeid,
                fid=feed.fid,
                abstime=feed.abstime,
            )

        async def like_trans(task: asyncio.Task[LikeData | None]):
            try:
                likedata = task.result()
            except:
                return
            if likedata is None:
                return

            if await self.qzone.like_app(likedata, True):
                await msg.reply_text("点赞失败")
            else:
                await msg.reply_text("点赞成功")

        task = self.add_hook_ref("storage", query_likedata(reply.message_id))
        task.add_done_callback(lambda t: self.add_hook_ref("command", like_trans(t)))

    # --------------------------------
    #              query
    # --------------------------------
    async def btn_dispatch(self, update: Update, context: CallbackContext):
        query: CallbackQuery = update.callback_query
        data: str = query.data
        prefix, data = data.split(":", maxsplit=1)
        switch = {"like": self.btn_like, "qr": self.btn_qr}
        await switch[prefix](query)

    async def btn_like(self, query: CallbackQuery):
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

        async def like_trans(likedata: LikeData | None):
            if likedata is None:
                try:
                    await query.answer(text=f"记录已丢失。可能是记录已被清理，或此消息本应发送失败。")
                except:
                    pass
                try:
                    await query.edit_message_reply_markup()
                except BadRequest:
                    pass
                except:
                    self.log.error("Failed to change button", exc_info=True)
                return

            if not await self.qzone.like_app(likedata, not unlike):
                await query.answer(text="点赞失败")
                return

            if unlike:
                btn = InlineKeyboardButton("Like", callback_data="like:" + data)
            else:
                btn = InlineKeyboardButton("Unlike", callback_data="like:-" + data)
            try:
                await query.edit_message_reply_markup(InlineKeyboardMarkup([[btn]]))
            except BadRequest:
                pass
            except:
                self.log.error("Failed to change button", exc_info=True)

        task = self.add_hook_ref("storage", query_likedata(data))
        task.add_done_callback(lambda t: self.add_hook_ref("button", like_trans(t.result())))

    async def btn_qr(self, query: CallbackQuery):
        self.log.info(f"QR! query={query.data}")
        _, command = str.split(query.data, ":", maxsplit=1)

        match command:
            case "refresh":
                self.hook_qr.refresh_flag.set()
            case "cancel":
                self.hook_qr.cancel_flag.set()
                await query.delete_message()
                self.hook_qr.qr_msg = None
            case _:
                self.log.warning(f"Unexpected qr button callback: {_}")
                await query.delete_message()
