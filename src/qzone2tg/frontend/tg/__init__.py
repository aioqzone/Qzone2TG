import logging
import re
from functools import wraps

import telegram
from qqqr.exception import UserBreak
from qzone2tg.middleware.utils import sementicTime
from qzone2tg.qzone.feed import QzCachedScraper
from telegram.error import NetworkError, TelegramError
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from telegram.ext.filters import Filters

from .base import RefreshBot
from .compress import LikeId
from .ui import br

logger = logging.getLogger(__name__)


class PollingBot(RefreshBot):
    commands = {
        "start": "Force login. Then refresh and resend all feeds.",
        "refresh": "Refresh and send any new feeds.",
        "resend": "Resend any unsent feeds.",
        'status': 'Get some runtime status.',
        "relogin": "Force relogin.",
        "help": "Send help message.",
    }

    def __init__(
        self,
        feedmgr: QzCachedScraper,
        token: str,
        accept_id: int,
        *,
        times_per_second: int = None,
        disable_notification: bool = False,
        network: dict = None,
        polling: dict = None,
        auto_start=False,
    ):
        super().__init__(
            feedmgr,
            token,
            accept_id,
            times_per_second=times_per_second,
            disable_notification=disable_notification,
            network=network
        )
        self.run_kwargs = {} if polling is None else polling
        self.auto_start = auto_start
        self.__proxy = 'proxy_url' in network

        dispatcher = self.update.dispatcher
        CA = Filters.chat(accept_id)
        dispatcher.add_handler(CommandHandler("start", self.onStart, filters=CA))
        dispatcher.add_handler(CommandHandler("refresh", self.onRefresh, filters=CA))
        dispatcher.add_handler(CommandHandler("resend", self.onSend, filters=CA))
        dispatcher.add_handler(CommandHandler('help', self.onHelp, filters=CA))
        dispatcher.add_handler(CommandHandler('status', self.onStatus, filters=CA))
        dispatcher.add_handler(CommandHandler('relogin', self.onRelogin, filters=CA))
        dispatcher.add_handler(CallbackQueryHandler(self.onButtonClick, run_async=True))

        try:
            self.update.bot.set_my_commands([
                telegram.BotCommand(command=k, description=v)
                for k, v in self.commands.items()
            ])
        except TelegramError as e:
            logger.warning(e.message)

    def checkAccess(self, update: telegram.Update, context: CallbackContext):
        if update.effective_chat.id != self.accept_id:
            logger.warning(f"illegal access: {update.effective_chat.id}")
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry. But bot won't answer unknown chat."
            )
            return False
        return True

    def onSend(self, *, reload=False):
        return super().onSend(reload=reload)

    def onRefresh(self, *, reload=False):
        self.onFetch(reload=reload)

    def onStart(self):
        self.onRefresh(reload=True)

    def onHelp(self):
        helpm = '\n'.join(f"/{k} - {v}" for k, v in self.commands.items())
        self.ui.bot.sendMessage(helpm)

    def onStatus(self):
        def fh(key: str):
            if (v := stat.get(key, None)):
                return sementicTime(v)
            else:
                return '还是在上次'

        stat = self.feedmgr.qzone.status()
        status = f"上次登录: {fh('last_login')}\n" \
                 f"上次心跳: {fh('last_heartbeat')}"
        self.ui.bot.sendMessage(status)

    def onRelogin(self):
        self.feedmgr.qzone.updateStatus(force_login=True)
        stat = self.feedmgr.qzone.status()
        if (v := stat['last_login']) is None:
            return
        msg = "重新登录: " + sementicTime(v)
        self.ui.bot.sendMessage(msg)

    def run(self):
        try:
            self.update.start_polling(**self.run_kwargs)
        except NetworkError as e:
            if self.__proxy:
                logger.fatal(
                    "Seems you're using proxy. \n"
                    "This might cause NetworkError for some reasons, such as confusing DNS inside GFW. "
                    "Try to trace your proxy traffic to lookup if anything goes out of expectancy. "
                    "Sometimes just waiting for a while works :D\n"
                    "See Q&A in Wiki for details."
                )
            else:
                logger.fatal(e.message, exc_info=True)
            return
        logger.info("start polling")
        super().run()

    def onButtonClick(self, update: telegram.Update, context):
        if not self.checkAccess(update, context): return
        query: telegram.CallbackQuery = update.callback_query
        data: str = query.data
        if data in (d := {
                'qr_refresh': self.ui.QrResend,
                'qr_cancel': self.ui.QrCanceled,
        }):
            d[data]()
        else:
            self.like(query)

    def like(self, query: telegram.CallbackQuery):
        logger.info("like post start")
        data: str = query.data

        def remove_button(msg_callback=None):
            ci = lambda x: msg_callback and msg_callback(x) or x
            kw = dict(parse_mode=telegram.ParseMode.HTML, reply_markup=None)
            if query.message.text_html is not None:
                query.edit_message_text(text=ci(query.message.text_html), **kw)
            elif query.message.caption_html is not None:
                query.edit_message_caption(caption=ci(query.message.caption_html), **kw)
            else:
                logger.warning('Message has neither text nor caption')

        if data.startswith('/'):
            try:
                if not self.feedmgr.likeAFile(data[1:]):
                    query.answer(text='点赞失败.')
                    return
            except FileNotFoundError:
                query.answer(text="该应用消息已超过服务器保留时限或保留上限, 超过时限的应用消息无法点赞.")
                remove_button()
            except UserBreak:
                return
        else:
            if not self.feedmgr.like(LikeId.fromstr(data).todict()):
                query.answer(text='点赞失败.')
                return

        remove_button(lambda m: m + br * 2 + '❤')
        logger.info("like post end")


class WebhookBot(PollingBot):
    def __init__(
        self,
        feedmgr: QzCachedScraper,
        token: str,
        accept_id: int,
        *,
        webhook: dict = None,
        **kwargs
    ):
        super().__init__(feedmgr, token, accept_id, polling=webhook, **kwargs)

    def run(self):
        server = re.search(r'(?:https?://)?([^/]*)/?',
                           self.run_kwargs.pop('server')).group(1)
        prefex = self.run_kwargs.pop('prefex', "")
        if prefex: prefex += '/'
        webhook_url = f"https://{server}/{prefex}{self._token}"
        try:
            self.update.start_webhook(
                **self.run_kwargs,
                url_path=self._token,
                webhook_url=webhook_url,
            )

        except NetworkError as e:
            logger.error(e.message, exc_info=True)
            return
        logger.info("start webhook")
        logger.debug(
            f"registerd webhook at {webhook_url}, listening at 127.0.0.1/{self._token}"
        )
        RefreshBot.run(self)
