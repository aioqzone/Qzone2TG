"""This module defines an app that interact with user using /command and inline markup buttons."""
import asyncio
from pathlib import Path
from typing import Type

from aioqzone.api.loginman import QrStrategy
from aioqzone.type.internal import LikeData
from qqqr.utils.net import ClientAdapter
from sqlalchemy.ext.asyncio import AsyncEngine
from telegram import BotCommand, Message, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from qzone3tg.app.hook import DefaultUpHook
from qzone3tg.settings import PollingConf, Settings

from ..base import BaseApp


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
        "like": "点赞指定的说说",
        "help": "帮助",
    }

    def __init__(self, client: ClientAdapter, store: AsyncEngine, conf: Settings) -> None:
        super().__init__(client, store, conf)
        self.fetch_lock = LockFilter()

    # --------------------------------
    #            hook init
    # --------------------------------
    from ._button import hook_taskerevent as _sub_taskerevent

    def _sub_defaultqrhook(self, base):
        from ._button import hook_defaultqr as _sub_defaultqrhook

        return _sub_defaultqrhook(self, super()._sub_defaultqrhook(base))

    def _sub_defaultuphook(self, base: Type[DefaultUpHook]):
        class get_reply(base):
            async def force_reply_answer(_self, msg) -> str | None:
                code = ""
                evt = asyncio.Event()

                def cb(update: Update, _):
                    nonlocal code
                    assert update.effective_message
                    code = update.effective_message.text or ""
                    code = code.strip()
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

        class interactapp_feedhook(base):
            async def HeartbeatRefresh(_self, num: int):
                if self.fetch_lock.locked:
                    self.log.warning("Heartbeat refresh skipped since fetch is running.")
                    return
                self.fetch_lock.acquire(await super().HeartbeatRefresh(num))  # type: ignore

            async def HeartbeatFailed(_self, exc: BaseException | None):
                await super().HeartbeatFailed(exc)
                lm = self.loginman
                qr_avil = lm.strategy != QrStrategy.forbid and not lm.qr_suppressed
                up_avil = lm.strategy != QrStrategy.force and not lm.up_suppressed
                if qr_avil or up_avil:
                    await self.bot.send_message(
                        self.admin, "/relogin 重新登陆，/help 查看帮助", disable_notification=True
                    )

        return interactapp_feedhook

    def register_handlers(self):
        # build chat filters
        ca_id = [self.conf.bot.admin]
        ca_un = []
        CA = filters.Chat(chat_id=ca_id, username=ca_un)

        has_fetch = ["start"]
        for command in set(i.split(maxsplit=1)[0] for i in self.commands):
            self.app.add_handler(
                CommandHandler(
                    command,
                    getattr(self, command, self.help),
                    filters=(CA | self.fetch_lock) if command in has_fetch else CA,
                    block=False,
                )
            )
        self.app.add_handler(CallbackQueryHandler(self.btn_qr, r"^qr:(refresh|cancel)$"))
        self.app.add_handler(CallbackQueryHandler(self.btn_like, r"^like:-?\d+$", block=False))

        from ._conversation.emoji import ASK_CUSTOM, CHOOSE_EID

        self.app.add_handler(
            ConversationHandler(
                entry_points=[
                    CallbackQueryHandler(self.btn_emoji, r"^emoji:$"),
                    CommandHandler("em", self.command_em, CA),
                ],
                states={
                    CHOOSE_EID: [MessageHandler(filters.Regex(r"^\d+$"), self.input_eid)],
                    ASK_CUSTOM: [
                        MessageHandler(filters.TEXT & (~filters.COMMAND), self.update_eid)
                    ],
                },
                fallbacks=[CommandHandler("cancel", self.cancel_custom, filters=CA)],
            )
        )

    async def set_commands(self):
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
        self.register_handlers()
        await self.set_commands()
        return await super().run()

    # --------------------------------
    #            command
    # --------------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        assert chat
        self.log.info("Start! chat=%d", chat.id)
        task = self.add_hook_ref("command", self.fetch(chat.id))
        self.fetch_lock.acquire(task)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from qzone3tg import DOCUMENT

        chat = update.effective_chat
        assert chat
        helpm = "\n".join(f"/{k} - {v}" for k, v in self.commands.items())
        helpm += "\n\n官方频道：@qzone2tg"
        helpm += "\n讨论群：@qzone2tg_discuss"
        helpm += f"\n文档：{DOCUMENT}/usage.html"
        await self.bot.send_message(chat.id, helpm)

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        assert chat
        if context.args and len(context.args) == 1 and context.args[0].lower() == "debug":
            await super().status(chat.id, debug=True)
        else:
            await super().status(chat.id)

    async def relogin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        assert chat
        with self.loginman.disable_suppress():
            try:
                await self.qzone.api.login.new_cookie()
            except:
                return

        if await self.restart_heartbeat():
            await self.bot.send_message(self.admin, "心跳已重启")

    async def like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        async def like_trans(likedata: LikeData):
            with self.loginman.disable_suppress():
                try:
                    succ = await self.qzone.like_app(likedata, True)
                except:
                    self.log.error("点赞失败", exc_info=True)
                    succ = False
            if succ:
                await msg.reply_text("点赞成功")
            else:
                await msg.reply_text("点赞失败")

        likedata = await query_likedata(reply.message_id)
        if likedata is None:
            return
        await like_trans(likedata)

    # --------------------------------
    #              query
    # --------------------------------
    from ._button import btn_like, btn_qr
    from ._conversation.emoji import btn_emoji, cancel_custom, command_em, input_eid, update_eid
