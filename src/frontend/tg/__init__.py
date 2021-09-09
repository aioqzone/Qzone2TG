import logging
import re
from datetime import datetime, time as Time, timedelta, timezone

import telegram
from qzone.exceptions import UserBreak
from qzone.feed import QZCachedScraper
from requests.exceptions import HTTPError
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    CallbackContext, CallbackQueryHandler, CommandHandler, Updater
)

from utils.decorator import Locked

from .compress import LikeId
from .ui import TgExtracter, TgUI, br, retry_once

logger = logging.getLogger(__name__)


class FakeObj:
    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class RefreshBot:
    flood_limit = 30

    def __init__(
        self,
        feedmgr: QZCachedScraper,
        token: str,
        accept_id: int,
        uin: int,
        *,
        daily: dict = None,
        proxy: dict = None,
    ):
        self.accept_id = accept_id
        self.feedmgr = feedmgr
        self._token = token
        self.uin = uin
        self.daily = daily

        self.update = Updater(token, use_context=True, request_kwargs=proxy)
        self.ui = TgUI(self.update.bot, accept_id)

        def cleanFeed(context):
            self.feedmgr.cleanFeed()

        self.update.job_queue.run_daily(cleanFeed, Time(0, 0, 0, 1))
        self.update.job_queue.run_custom(cleanFeed, {})

    def __del__(self):
        self.update.stop()

    def register_period_refresh(self):
        kw = dict(
            callback=lambda c: self.onFetch(c.bot, False),
            days=tuple(self.daily.get('days', range(7)))
        )
        if 'time' in self.daily and self.daily['time']:
            if isinstance(self.daily.time, str):
                timelist = self.daily.time.split()
            else:
                timelist = list(self.daily.time)
            for i in timelist:
                self.update.job_queue.run_daily(
                    time=Time.fromisoformat(i), name='period_refresh_' + i, **kw
                )
        else:
            self.update.job_queue.run_daily(
                time=(datetime.utcnow() + timedelta(hours=8)).time(),
                name='period_refresh',
                **kw
            )
        logger.info('periodically refresh registered.')

    def run(self):
        assert self.daily, 'refresh bot must refresh!'
        self.register_period_refresh()
        logger.info("start refreshing")
        self.update.idle()

    def onSend(self, update: telegram.Update, context: CallbackContext, reload=False):
        @Locked(
            lambda: logger.info('onSend: new send excluded.') or context.bot.
            send_message(
                chat_id=self.accept_id, text="Sorry. But the bot is sending already."
            )
        )
        def send(context):
            err = 0
            new = self.feedmgr.db.getFeed(
                cond_sql='' if reload else 'is_sent IS NULL OR is_sent=0',
                plugin_name='tg',
                order=True,
            )
            if new == False: return self.ui.fetchError('数据库出错, 请检查数据库')

            for i in new:
                try:
                    i = TgExtracter(i, self.uin)
                    if i.isBlocked: continue
                    send_w_retry = retry_once(
                        self.ui.contentReady, lambda exc: f"feed {i.feed}: {exc}"
                    )
                    send_w_retry(
                        *i.content(),
                        i.likeButton() if hasattr(self, 'like') else None,
                    )
                    self.feedmgr.db.setPluginData('tg', i.feed.fid, is_sent=1)
                except Exception as e:
                    logger.error(f"{i.feed}: {str(e)}", exc_info=True)
                    err += 1
                    continue
            self.ui.fetchEnd(len(new) - err, err)

        self.update.job_queue.run_custom(send, {})

    def onFetch(self, bot: telegram.Bot, reload: bool):
        cmd = "force-refresh" if reload else "refresh"

        logger.info(f"{self.accept_id}: start {cmd}")

        @Locked(
            lambda: logger.info('onFetch: new fetch excluded.') or bot.send_message(
                chat_id=self.accept_id, text="Sorry. But the bot is fetching already."
            )
        )
        def fetch(context: CallbackContext):
            try:
                self.feedmgr.fetchNewFeeds(reload)
            except TimeoutError:
                self.ui.fetchError("爬取超时, 刷新或许可以)")
                return
            except HTTPError:
                self.ui.fetchError('爬取出错, 刷新或许可以)')
                return
            except UserBreak:
                self.ui.QrCanceled()
                return
            except Exception as e:
                logger.error(str(e), exc_info=True, stack_info=True)
                self.ui.fetchError()
                return
            self.onSend(
                FakeObj(effective_chat=FakeObj(id=self.accept_id)), context, reload
            )

        self.update.job_queue.run_custom(fetch, {})


class PollingBot(RefreshBot):
    reload_on_start = True

    def __init__(
        self,
        feedmgr: QZCachedScraper,
        token: str,
        accept_id: int,
        uin: int,
        *,
        daily: dict = None,
        proxy: dict = None,
        polling: dict = None,
        auto_start=False,
    ):
        super().__init__(feedmgr, token, accept_id, uin, daily=daily, proxy=proxy)
        self.run_kwargs = {} if polling is None else polling
        self.auto_start = auto_start
        self.__proxy = proxy

        dispatcher = self.update.dispatcher
        dispatcher.add_handler(CommandHandler("start", self.onStart))
        dispatcher.add_handler(CommandHandler("refresh", self.onRefresh))
        dispatcher.add_handler(CommandHandler("resend", self.onSend))
        dispatcher.add_handler(CommandHandler('help', self.onHelp))
        dispatcher.add_handler(CallbackQueryHandler(self.onButtonClick))

        commands = [
            telegram.BotCommand(
                command="start",
                description="Force login. Then refresh and resend all feeds."
            ),
            telegram.BotCommand(
                command="refresh", description="Refresh and send any new feeds.."
            ),
            telegram.BotCommand(
                command="resend", description="Resend any unsent feeds."
            ),
            telegram.BotCommand(command="help", description="Send this message.")
        ]
        try:
            self.update.bot.set_my_commands(commands)
        except TelegramError as e:
            logger.warning(e.message)

    def checkAccess(self, bot, chat_id: int):
        if chat_id != self.accept_id:
            logger.warning(f"illegal access: {chat_id}")
            bot.send_message(
                chat_id=chat_id, text="Sorry. But bot won't answer unknown chat."
            )
            return False
        return True

    def onSend(self, update: telegram.Update, context: CallbackContext, reload=False):
        if self.checkAccess(context.bot, update.effective_chat.id):
            return super().onSend(update, context, reload)

    def onRefresh(
        self, update: telegram.Update, context: CallbackContext, reload=False
    ):
        if self.checkAccess(context.bot, update.effective_chat.id):
            self.onFetch(context.bot, reload)

    def onStart(self, update: telegram.Update, context):
        self.onRefresh(update, context, reload=self.reload_on_start)
        self.register_period_refresh()

    def onHelp(self, update, context: CallbackContext):
        if self.checkAccess(context.bot, update.effective_chat.id):
            context.bot.send_message(
                chat_id=self.accept_id,
                text="/start - Force login. Then refresh and resend all feeds.\n"
                "/refresh - Refresh and send any new feeds.\n"
                "/resend - Resend any unsent feeds.\n"
                "/help - Send this message."
            )

    def run(self):
        try:
            self.update.start_polling(**self.run_kwargs)
        except NetworkError as e:
            if self.__proxy:
                logger.fatal(
                    "Seems you're using `proxy + polling`. "
                    "This might cause NetworkError for some unknown reason. Try using `webhook mode` :D \n"
                    "Otherwise maybe wait for a while is enough. See FAQ in Wiki for details."
                )
            else:
                logger.fatal(e.message, exc_info=True, stack_info=True)
            return
        logger.info("start polling")
        self.idle()

    def idle(self):
        if self.auto_start:
            logger.info('auto start')
            self.onStart(
                update=FakeObj(effective_chat=FakeObj(id=self.accept_id)),
                context=FakeObj(bot=self.update.bot)
            )
        else:
            self.ui.bot.sendMessage(
                "You've disabled 'auto start'. "
                "Then you may send /start to force refresh and resend all feeds, "
                "or send /refresh to present a normal refresh.",
            )
        self.register_period_refresh()
        self.update.idle()

    def onButtonClick(self, update: telegram.Update, context):
        query: telegram.CallbackQuery = update.callback_query
        data: str = query.data
        if not self.checkAccess(context.bot, update.effective_chat.id): return
        if data in (d := {
                'qr_refresh': self.ui.QrResend,
                'qr_cancel': self.ui._cancel,
        }):
            d[data]()
        else:
            self.like(query)

    def like(self, query: telegram.CallbackQuery):
        logger.info("like post start")
        data: str = query.data

        def remove_button(msg_callback=None):
            ci = lambda f, x: f and f(x) or x                             # and > or
            if query.message.text_html:
                query.edit_message_text(
                    text=ci(msg_callback, query.message.text_html),
                    parse_mode=telegram.ParseMode.HTML
                )
            else:
                query.edit_message_caption(
                    caption=ci(msg_callback, query.message.caption_html),
                    parse_mode=telegram.ParseMode.HTML
                )

        if data.startswith('/'):
            try:
                if not self.feedmgr.likeAFile(data[1:]):
                    query.answer(text='点赞失败.')
                    return
            except FileNotFoundError:
                query.answer(text="该应用消息已超过服务器保留时限或保留上限, 超过时限的应用消息无法点赞.")
                remove_button()
            except UserBreak:
                self.ui.QrCanceled()
        else:
            if not self.feedmgr.like(LikeId.fromstr(data).todict()):
                query.answer(text='点赞失败.')
                return

        remove_button(lambda m: m + br * 2 + '❤')
        logger.info("like post end")


class WebhookBot(PollingBot):
    def __init__(
        self,
        feedmgr: QZCachedScraper,
        token: str,
        accept_id: int,
        uin: int,
        *,
        webhook: dict = None,
        **kwargs
    ):
        super().__init__(feedmgr, token, accept_id, uin, **kwargs, polling=webhook)

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
            logger.error(e.message, exc_info=True, stack_info=True)
            return
        logger.info("start webhook")
        logger.debug(
            f"registerd webhook at {webhook_url}, listening at 127.0.0.1/{self._token}"
        )
        self.idle()
