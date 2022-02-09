"""This module defines an app that interact with user using /command and inline markup buttons."""
import asyncio
from typing import cast, Optional, Union

from aiohttp import ClientSession as Session
from aioqzone.type import LikeData
from aioqzone.type import PersudoCurkey
from aioqzone_feed.type import BaseFeed
from telegram import BotCommand
from telegram import CallbackQuery
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Update
from telegram.ext import CallbackContext
from telegram.ext import CallbackQueryHandler
from telegram.ext import CommandHandler
from telegram.ext import Dispatcher
from telegram.ext import Filters
from telegram.ext import MessageFilter

from ..settings import PollingConf
from ..settings import Settings
from ..utils.iter import anext
from .base import BaseApp
from .base import BaseAppHook
from .storage import AsyncEngine
from .storage import DefaultStorageHook
from .storage.orm import FeedOrm


class InteractAppHook(BaseAppHook):
    def like_markup(self, feed: BaseFeed):
        if feed.unikey is None: return
        curkey = LikeData.persudo_curkey(feed.uin, feed.abstime)
        likebtn = InlineKeyboardButton('Like', callback_data='like:' + curkey)
        return InlineKeyboardMarkup([[likebtn]])

    def qr_markup(self):
        btnrefresh = InlineKeyboardButton('刷新', callback_data='qr:refresh')
        btncancel = InlineKeyboardButton('取消', callback_data='qr:cancel')
        return InlineKeyboardMarkup([[btnrefresh, btncancel]])


class InteractStorageHook(DefaultStorageHook):
    async def query_likedata(self, persudo_curkey: str) -> Optional[LikeData]:
        p = PersudoCurkey.from_str(persudo_curkey)
        r = await self.get(FeedOrm.uin == p.uin, FeedOrm.abstime == p.abstime)
        if r is None: return None
        feed, _ = r
        if feed.unikey is None: return
        return LikeData(
            unikey=str(feed.unikey),
            curkey=str(feed.curkey) or LikeData.persudo_curkey(feed.uin, feed.abstime),
            appid=feed.appid,
            typeid=feed.typeid,
            fid=feed.fid,
            abstime=feed.abstime
        )


class LockFilter(MessageFilter):
    def __init__(self) -> None:
        super().__init__()
        self.locked = False

    def filter(self, message):
        return not self.locked

    def acquire(self, task: asyncio.Task):
        self.locked = True
        task.add_done_callback(lambda _: setattr(self, 'locked', False))


class InteractApp(BaseApp):
    hook_cls = InteractAppHook
    store_cls = InteractStorageHook

    commands = {
        "start": "刷新",
        "refresh": "刷新",
        'status': '获取运行状态',
        "relogin": "强制重新登陆",
        "help": "帮助",
    }

    def __init__(self, sess: Session, store: AsyncEngine, conf: Settings) -> None:
        super().__init__(sess, store, conf)
        self.fetch_lock = LockFilter()

        if conf.bot.reload_on_start:
            self.commands['start'] = f"获取{conf.qzone.dayspac}天内的全部说说，覆盖数据库"
        else:
            self.commands['refresh'] = "还是刷新"

        self.set_commands()

    @property
    def store(self) -> InteractStorageHook:
        return cast(InteractStorageHook, super().store)

    def set_commands(self):
        # build chat filters
        ca_id = [self.conf.bot.admin]
        ca_un = []
        CA = Filters.chat(chat_id=ca_id, username=ca_un)

        dispatcher: Dispatcher = self.updater.dispatcher
        has_fetch = ['start', 'refresh']
        for command in self.commands:
            dispatcher.add_handler(
                CommandHandler(
                    command,
                    getattr(self, command, self.help),
                    filters=(CA | self.fetch_lock) if command in has_fetch else CA
                )
            )
        dispatcher.add_handler(CallbackQueryHandler(self.btn_dispatch, run_async=True))

        try:
            self.updater.bot.set_my_commands([
                BotCommand(command=k, description=v) for k, v in self.commands.items()
            ])
        except:
            self.log.error("Error in setting commands", exc_info=True)

    async def run(self):
        if isinstance(self.conf.bot.init_args, PollingConf):
            self.updater.start_polling(**self.conf.bot.init_args.dict())
        else:
            token = self.conf.bot.token
            assert token
            kw = self.conf.bot.init_args.dict(exclude={'destination', 'cert', 'key'})
            safe_asposix = lambda p: p and p.as_posix()
            self.updater.start_webhook(
                url_path=token.get_secret_value(),
                webhook_url=self.conf.bot.init_args.webhook_url(token).get_secret_value(),
                cert=safe_asposix(self.conf.bot.init_args.cert),
                key=safe_asposix(self.conf.bot.init_args.key),
                **kw
            )
        return await super().run()

    def start(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        self.log.info('Start! chat=%d', chat.id)
        task = self.forward.add_hook_ref(
            'command',
            super().fetch(chat.id, reload=self.conf.bot.reload_on_start)
        )
        self.fetch_lock.acquire(task)

    def refresh(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        self.log.info('Refresh! chat=%d', chat.id)
        task = self.forward.add_hook_ref('command', super().fetch(chat.id, reload=False))
        self.fetch_lock.acquire(task)

    def help(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        helpm = '\n'.join(f"/{k} - {v}" for k, v in self.commands.items())
        helpm += '\n\n讨论群：@qzone2tg_discuss'
        task = self.forward.add_hook_ref(
            'command', anext(self.forward.bot.send_message(chat.id, helpm))
        )

    def status(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        statusm = "阿巴阿巴"
        task = self.forward.add_hook_ref(
            'command', anext(self.forward.bot.send_message(chat.id, statusm))
        )

    def relogin(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        assert chat
        task = self.forward.add_hook_ref('command', self.qzone.api.login.new_cookie())

    def btn_dispatch(self, update: Update, context: CallbackContext):
        query: CallbackQuery = update.callback_query
        data: str = query.data
        prefix, data = data.split(':', maxsplit=1)
        switch = {'like': self.like, 'qr': self.qr}
        switch[prefix](query)

    def like(self, query: CallbackQuery):
        self.log.info(f'Like! query={query.data}')
        _, data = str.split(query.data, ':', maxsplit=1)
        if unlike := data.startswith('-'): data = data.removeprefix('-')

        def like_trans(likedata: Optional[LikeData]):
            if likedata is None:
                query.answer(text='记录丢失，请检查数据库')
                try:
                    query.edit_message_reply_markup()
                except:
                    self.log.error('Failed to change button', exc_info=True)
                return

            task = self.forward.add_hook_ref('button', self.qzone.like_app(likedata, not unlike))
            task.add_done_callback(check_succ)

        def check_succ(succ: asyncio.Task[bool]):
            try:
                assert succ.result()
            except:
                query.answer(text='点赞失败')
                return

            if not unlike:
                btn = InlineKeyboardButton('Like', callback_data="like:" + data)
            else:
                btn = InlineKeyboardButton('Unlike', callback_data="like:-" + data)
            try:
                query.edit_message_reply_markup(InlineKeyboardMarkup([[btn]]))
            except:
                self.log.error('Failed to change button', exc_info=True)

        task = self.forward.add_hook_ref('storage', self.store.query_likedata(data))
        task.add_done_callback(lambda t: like_trans(t.result()))

    def qr(self, query: CallbackQuery):
        self.log.info(f'QR! query={query.data}')
        _, command = str.split(query.data, ':', maxsplit=1)
        switch = {'refresh': self.forward.resend, 'cancel': self.forward.cancel}
        f = switch[command]
        assert f
        task = self.forward.add_hook_ref('button', f())
