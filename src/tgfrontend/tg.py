import logging
import re
from datetime import time

import telegram
from qzonebackend.feed import QZCachedScraper
from requests.models import HTTPError
from telegram.error import NetworkError
from telegram.ext import (
    CallbackContext, CallbackQueryHandler, CommandHandler, Updater
)

from . import *
from .compress import LikeId
from .tg_uihook import TgUI, br, send_feed

logger = logging.getLogger("telegram")


class FakeObj:
    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class RefreshBot:
    def __init__(
        self,
        feedmgr: QZCachedScraper,
        token: str,
        accept_id: list,
        *,
        interval=0,
        proxy: dict = None,
    ):
        self.accept_id = accept_id
        self.feedmgr = feedmgr
        self._token = token
        self.interval = interval
        self.fetching = False

        self.update = Updater(token, use_context=True, request_kwargs=proxy)
        self.update.job_queue.run_daily(
            lambda c: self.feedmgr.cleanFeed(), time(0, 0, 0, 1), name='cleanFeed'
        )
        self.ui = TgUI(self.update.bot)

    def register_period_refresh(self):
        if self.interval > 0:
            self.update.job_queue.run_repeating(
                lambda c: self.onFetch(c.bot, False),
                self.interval,
                name='period_refresh'
            )
        logger.info('periodically refresh registered.')

    def run(self):
        assert len(self.accept_id) == 1, "refresh bot can only send to specific user!"
        assert self.interval > 0, 'refresh bot must refresh!'
        self.chat_id = self.accept_id[0]
        self.register_period_refresh()
        logger.info("start refreshing")
        self.update.idle()

    def onFetch(self, bot: telegram.Bot, reload: bool):
        cmd = "force-refresh" if reload else "refresh"

        if self.chat_id in self.accept_id:
            logger.info(f"{self.chat_id}: start {cmd}")
        else:
            logger.info(f"{self.chat_id}: illegal access")
            bot.send_message(
                chat_id=self.chat_id, text="Sorry. But bot won't answer unknown chat."
            )
        if self.fetching:
            logger.info('onFetch: new fetch excluded.')
            bot.send_message(
                chat_id=self.chat_id, text="Sorry. But the bot is fetching already."
            )
            return
        else:
            self.fetching = True

        def fetch(context):
            try:
                new = self.feedmgr.fetchNewFeeds(reload)
            except TimeoutError:
                self.ui.fetchError("爬取超时, 刷新或许可以)")
                return
            except HTTPError:
                self.ui.fetchError('爬取出错, 刷新或许可以)')
                return
            except Exception as e:
                logger.error(str(e), exc_info=True, stack_info=True)
                self.ui.fetchError()
                return

            err = 0
            for i in new:
                try:
                    send_feed(bot, self.chat_id, i, hasattr(self, 'like'))
                except Exception as e:
                    logger.error(f"{i.hash}: {str(e)}", exc_info=True, stack_info=True)
                    err += 1
                    continue

            self.ui.fetchEnd(len(new) - err, err)
            logger.info(f"{cmd} end")
        def safe_fetch(context):
            try:
                fetch(context)
            except Exception:
                logger.error('uncought exception in fetch.', exc_info=True, stack_info=True)
            finally:
                self.fetching = False
        
        self.update.job_queue.run_custom(safe_fetch, {})


class PollingBot(RefreshBot):
    reload_on_start = False

    def __init__(
        self,
        feedmgr: QZCachedScraper,
        token: str,
        accept_id: list,
        *,
        interval=0,
        proxy: dict = None,
        polling: dict = None,
        auto_start=True,
    ):
        super().__init__(feedmgr, token, accept_id, interval=interval, proxy=proxy)
        self.run_kwargs = {} if polling is None else polling
        self.auto_start = auto_start

        dispatcher = self.update.dispatcher
        dispatcher.add_handler(CommandHandler("start", self.onStart))
        dispatcher.add_handler(CommandHandler("refresh", self.onRefresh))
        dispatcher.add_handler(CallbackQueryHandler(self.onButtonClick))

    def onRefresh(
        self, update: telegram.Update, context: CallbackContext, reload=False
    ):
        self.chat_id = self.ui.chat_id = update.effective_chat.id
        self.onFetch(context.bot, reload)

    def onStart(self, update: telegram.Update, context):
        logger.info('Bot starting')
        self.onRefresh(update, context, reload=self.reload_on_start)
        self.register_period_refresh()

    def run(self):
        try:
            self.update.start_polling(**self.run_kwargs)
        except NetworkError as e:
            logger.error(e.message, exc_info=True, stack_info=True)
            self.update.stop()
            return
        logger.info("start polling")
        self.idle()

    def idle(self):
        if self.auto_start and len(self.accept_id) == 1:
            logger.info('auto start')
            self.onStart(
                update=FakeObj(effective_chat=FakeObj(id=self.accept_id[0])),
                context=FakeObj(bot=self.update.bot)
            )
        self.update.idle()

    def onButtonClick(self, update: telegram.Update, context):
        query: telegram.CallbackQuery = update.callback_query
        data: str = query.data
        self.chat_id = self.ui.chat_id = update.effective_chat.id
        if data in (d := {
                'qr_refresh': self.ui.QrResend,
        }):
            d[data]()
        else:
            self.like(query)

    def like(self, query: telegram.CallbackQuery):
        logger.info("like post start")
        data: str = query.data
        if '/' in data:
            try:
                if not self.feedmgr.likeAFile(data + ".json"):
                    query.answer(text='点赞失败.')
                    return
            except FileNotFoundError:
                query.answer(text="该应用消息已超过服务器保留时限或保留上限, 超过时限的应用消息无法点赞.")
                query.edit_message_text(
                    text=query.message.text_html, parse_mode=telegram.ParseMode.HTML
                )
                return
        else:
            if not self.feedmgr.like(LikeId.fromstr(data)):
                query.answer(text='点赞失败.')
                return
        query.edit_message_text(
            text=query.message.text_html + br * 2 + '❤',
            parse_mode=telegram.ParseMode.HTML
        )
        logger.info("like post end")


class WebhookBot(PollingBot):
    def __init__(
        self,
        feedmgr: QZCachedScraper,
        token: str,
        accept_id: list,
        *,
        webhook: dict = None,
        **kwargs
    ):
        super().__init__(feedmgr, token, accept_id, **kwargs, polling=webhook)

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
            self.update.stop()
            return
        logger.info("start webhook")
        logger.debug(
            f"registerd webhook at {webhook_url}, listening at 127.0.0.1/{self._token}"
        )
        self.idle()
