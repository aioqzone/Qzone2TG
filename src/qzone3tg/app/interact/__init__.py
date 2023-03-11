"""This module defines an app that interact with user using /command and inline markup buttons."""
import asyncio

from aioqzone.type.internal import LikeData
from qqqr.utils.net import ClientAdapter
from sqlalchemy.ext.asyncio import AsyncEngine
from telegram import BotCommand, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from qzone3tg.app.storage import StorageEvent
from qzone3tg.app.storage.blockset import BlockSet
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


class InteractApp(BaseApp):
    commands = {
        "start": "刷新",
        "status": "获取运行状态",
        "relogin": "强制重新登陆",
        "like": "点赞指定的说说",
        "help": "帮助",
        "block": "黑名单管理",
    }

    def __init__(self, client: ClientAdapter, store: AsyncEngine, conf: Settings) -> None:
        super().__init__(client, store, conf)
        self.fetch_lock = LockFilter()

    # --------------------------------
    #            hook init
    # --------------------------------
    from ._button import qrevent_hook as _sub_qrevent
    from ._button import queueevent_hook as _sub_queueevent
    from ._hook import feedevent_hook as _sub_feedevent
    from ._hook import heartbeatevent_hook as _sub_heartbeatevent
    from ._hook import upevent_hook as _sub_upevent

    def init_queue(self):
        super().init_queue()
        self.blockset = BlockSet(self.engine)

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

        from ._conversation.emoji import EmCvState

        self.app.add_handler(
            ConversationHandler(
                entry_points=[
                    CallbackQueryHandler(self.btn_emoji, r"^emoji:$"),
                    CommandHandler("em", self.command_em, CA),
                ],
                states={
                    EmCvState.CHOOSE_EID: [
                        MessageHandler(filters.Regex(r"^\d+$"), self.input_eid)
                    ],
                    EmCvState.ASK_CUSTOM: [
                        MessageHandler(filters.TEXT & (~filters.COMMAND), self.update_eid)
                    ],
                },
                fallbacks=[CommandHandler("cancel", self.cancel_custom, filters=CA)],
                per_chat=False,
            )
        )

    async def set_commands(self):
        try:
            await self.bot.set_my_commands(
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
        self.log.debug("Start! chat=%d", chat.id)
        if self._tasks["fetch"]:
            self.log.warning("a fetch task is pending, cancel.")
            self.clear("fetch")
        task = self.add_hook_ref("fetch", self._fetch(chat.id))
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
        match context.args:
            case ["debug"]:
                await super().status(chat.id, debug=True)
            case _:
                await super().status(chat.id)

    async def relogin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        assert chat
        with self.loginman.disable_suppress():
            try:
                await self.qzone.login.new_cookie()
            except:
                return

        # `LoginSuccess` hooks will restart heartbeat

    async def like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        assert msg
        reply = msg.reply_to_message
        if not reply:
            await msg.reply_text("使用 /like 时，您需要回复一条消息。")
            return

        async def query_likedata(mid: int):
            feed = await self[StorageEvent].Mid2Feed(reply.message_id)
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
                    succ = await self.qzone.internal_dolike_app(
                        likedata.appid, likedata.unikey, likedata.curkey, True
                    )
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
    from ._block import block
    from ._button import btn_like, btn_qr
    from ._conversation.emoji import btn_emoji, cancel_custom, command_em, input_eid, update_eid
