import logging
import re
from requests.models import HTTPError

import telegram
from qzonebackend.feed import FeedOperation, day_stamp
from qzonebackend.qzfeedparser import QZFeedParser as Parser
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import (
    CallbackContext, CallbackQueryHandler, CommandHandler, Updater
)

from .compress import LikeId
from .hook import TgUiHook

br = '\n'
hr = '==============='

SUPPORT_TYPEID = (0, 5)
SUPPORT_APPID = (4, 202, 311)
APP_NAME = {4: 'QQ相册', 202: '微信', 311: 'QQ空间'}

logger = logging.getLogger("telegram")


def html_link(txt, link) -> str:
    return f'<a href="{link}">{txt}</a>'


class UI(TgUiHook):
    bot: telegram.Bot
    chat_id: int

    def __init__(self, bot, chat_id=None) -> None:
        super().__init__()
        self.bot = bot
        if chat_id is not None: self.chat_id = chat_id

    def QrFetched(self, png: bytes):
        self.qr_msg = self.bot.send_photo(
            chat_id=self.chat_id,
            photo=png,
            caption='扫码登陆.',
        )

    def QrExpired(self, png: bytes):
        self.qr_msg = self.qr_msg.edit_media(
            media=telegram.InputMediaPhoto(
                png,
                caption='二维码已过期, 重新扫描此二维码.',
            )
        )

    def QrScanSucceessed(self):
        if self.qr_msg.delete():
            del self.qr_msg

    def QrSent(self):
        pass

    def loginSuccessed(self):
        self.ui_msg = self.bot.send_message(
            chat_id=self.chat_id,
            text='✔ 登录成功',
            parse_mode=telegram.ParseMode.MARKDOWN_V2
        )

    def loginFailed(self, msg="unknown"):
        self.bot.send_message(
            chat_id=self.chat_id,
            text=f'❌ 登录失败: __{msg}__',
            parse_mode=telegram.ParseMode.MARKDOWN_V2
        )

    def pageFetched(self, msg):
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_markdown_v2 + '\n✔ ' + msg,
                parse_mode=telegram.ParseMode.MARKDOWN_V2
            )
        else:
            self.ui_msg = self.bot.send_message(
                chat_id=self.chat_id,
                text='✔ ' + msg,
                parse_mode=telegram.ParseMode.MARKDOWN_V2
            )

    def fetchEnd(self):
        if self.ui_msg.delete(): del self.ui_msg

    def fetchError(self, msg=None):
        if hasattr(self, 'ui_msg'):
            if msg is None: msg = 'Ooops... 出错了qvq'
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_markdown_v2 + '\n❌ ' + msg,
                parse_mode=telegram.ParseMode.MARKDOWN_V2
            )
            del self.ui_msg


def send_photos(bot: telegram.Bot, chat, img: list, caption: str = ""):
    for i in range(len(img)):
        try:
            bot.send_photo(
                chat_id=chat,
                photo=img[i],
                caption=caption.format(i + 1),
                disable_notification=True
            )
        except BadRequest as e:
            bot.send_message(
                chat_id=chat,
                text=caption.format(i + 1) + br +
                '(bot温馨提示: %s好像没发过来?)' % html_link("图片", img[i]),
                disable_web_page_preview=False,
                parse_mode=telegram.ParseMode.HTML
            )
            logger.warning(e.message)
        except TimedOut as e:
            logger.warning(e.message)


def send_feed(bot: telegram.Bot, chat, feed: Parser):
    if feed.appid not in SUPPORT_APPID: return
    if feed.typeid not in SUPPORT_TYPEID: return

    msg = feed.nickname + feed.feedstime

    if feed.typeid == 5:
        msg += "转发了{forward}的说说:"
    else:
        msg += "发表了说说:"
    msg += br * 2
    msg += feed.parseText()

    if feed.isLike:
        msg += br + br + '❤'
        rpl = None
    else:
        if feed.appid == 311:
            likeid = LikeId(311, feed.typeid, feed.feedkey, *feed.uckeys).tostr()
        else:
            likeid = f'{day_stamp(feed.abstime)}/{feed.hash}'
        btnLike = telegram.InlineKeyboardButton("Like", callback_data=likeid)
        rpl = telegram.InlineKeyboardMarkup([[btnLike]])

    if feed.appid not in (4, 311) or (feed.typeid == 5):
        #TODO: forward
        if (forward := feed.parseForward()) is None:
            logger.warning(
                f"{feed.hash}: cannot parse forward text. appid={feed.appid}, typeid={feed.typeid}"
            )
            msg = msg.format(forward=APP_NAME[feed.appid])
        else:
            forward_nick, forward_link, forward_text = forward
            msg = msg.format(forward=html_link('@' + forward_nick, forward_link)) + br
            msg += hr + br
            msg += '@' + forward_nick + ': '
            msg += forward_text

    img = feed.parseImage()
    if len(img) == 1: msg += br + html_link('P1', img[0])
    elif img: msg += f"{br}(bot温馨提示: 多图预警x{len(img)})"

    try:
        bot.send_message(
            chat_id=chat,
            text=msg,
            parse_mode=telegram.ParseMode.HTML,
            disable_web_page_preview=len(img) != 1,
            reply_markup=rpl
        )
    except TimedOut as e:
        logger.warning(e.message)
    except NetworkError as e:
        logger.error(f"{feed.hash}: {e.message}")

    if len(img) > 1:
        send_photos(bot, chat, img, f'{feed.nickname}于{feed.feedstime}')


class FakeObj:
    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class PollingBot:
    update: Updater
    reload_on_start = False

    def __init__(
        self,
        feedmgr: FeedOperation,
        token: str,
        accept_id: list,
        *,
        interval=0,
        proxy: dict = None,
        polling: dict = None,
        auto_start=True,
    ):
        self.accept_id = accept_id
        self.feedmgr = feedmgr
        self.run_kwargs = {} if polling is None else polling
        self._token = token
        self.interval = interval
        self.auto_start = auto_start

        self.update = Updater(token, use_context=True, request_kwargs=proxy)
        self.ui = UI(self.update.bot)
        dispatcher = self.update.dispatcher
        dispatcher.add_handler(CommandHandler("start", self.onStart))
        dispatcher.add_handler(CommandHandler("refresh", self.onRefresh))
        dispatcher.add_handler(CallbackQueryHandler(self.like))

    def onRefresh(
        self, update: telegram.Update, context: CallbackContext, reload=False
    ):
        self.chat_id = update.effective_chat.id
        self.ui.chat_id = self.chat_id
        self.onFetch(context.bot, reload)

    def onStart(self, update: telegram.Update, context):
        logger.info('Bot starting')
        self.onRefresh(update, context, reload=self.reload_on_start)
        self.register_period_refresh()

    def register_period_refresh(self):
        if self.interval > 0:
            self.update.job_queue.run_repeating(
                lambda c: self.onFetch(c.bot, False),
                self.interval,
                name='period_refresh'
            )
        logger.info('periodically refresh registered.')

    def run(self):
        try:
            self.update.start_polling(**self.run_kwargs)
        except NetworkError as e:
            logger.error(e.message)
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

    def like(self, update: telegram.Update, context):
        logger.info("like post start")
        query: telegram.CallbackQuery = update.callback_query
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
            text=query.message.text_html + br + '❤', parse_mode=telegram.ParseMode.HTML
        )
        logger.info("like post end")

    def onFetch(self, bot: telegram.Bot, reload: bool):
        cmd = "force-refresh" if reload else "refresh"

        if self.chat_id in self.accept_id:
            logger.info(f"{self.chat_id}: start {cmd}")
        else:
            logger.info(f"{self.chat_id}: illegal access")
            bot.send_message(
                chat_id=self.chat_id, text="Sorry. But bot won't answer unknown chat."
            )

        try:
            new = self.feedmgr.fetchNewFeeds(reload)
        except TimeoutError:
            self.ui.fetchError("爬取超时, 刷新或许可以)")
            return
        except HTTPError:
            self.ui.fetchError('爬取出错, 刷新或许可以)')
            return
        except Exception:
            self.ui.fetchError()
            return

        for i in new:
            send_feed(bot, self.chat_id, i)

        bot.send_message(
            chat_id=self.chat_id, text=f"成功爬取{len(new)}条说说." if new else "您已经跟上了时代✔"
        )
        logger.info(f"{cmd} end")


class WebhookBot(PollingBot):
    def __init__(
        self,
        feedmgr: FeedOperation,
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
            logger.error(e.message)
            self.update.stop()
            return
        logger.info("start webhook")
        logger.debug(
            f"registerd webhook at {webhook_url}, listening at 127.0.0.1/{self._token}"
        )
        self.idle()
