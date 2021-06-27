import logging
import time

import telegram
from qzonebackend.feed import *
from qzonebackend.qzfeedparser import QZFeedParser as Parser
from qzonebackend.qzone import *
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import (
    CallbackContext, CallbackQueryHandler, CommandHandler, Updater
)

from .compress import LikeId

br = '\n'
SUPPORT_TYPEID = (0, 5)
logger = logging.getLogger("telegram")


def make_link(txt, link) -> str:
    return f'<a href="{link}">{txt}</a>'


def send_photos(bot: telegram.Bot, chat, img: list, caption: str = ""):
    for i in range(len(img)):
        try:
            bot.send_photo(
                chat_id=chat,
                photo=img[i],
                caption=caption.format(i + 1),
                disable_notification=True
            )
        except BadRequest:
            bot.send_message(
                chat_id=chat,
                text=caption.format(i + 1) + br +
                '(bot温馨提示: %s好像没发过来?)' % make_link("图片", img[i]),
                disable_web_page_preview=False,
                parse_mode=telegram.ParseMode.HTML
            )
        except TimedOut as e:
            logger.warning(e.message)


def send_feed(bot: telegram.Bot, chat, feed: dict):
    psr = Parser(feed)
    if psr.typeid not in SUPPORT_TYPEID: return

    msg = psr.nickname + psr.feedstime

    if psr.typeid == 5:
        msg += "转发了{forward}的说说:"
    else:
        msg += "发表了说说:"
    msg += br * 2
    msg += psr.parseText()

    if psr.isLike:
        msg += br + '❤'
        rpl = None
    else:
        if int(feed["appid"]) == 311:
            likeid = LikeId(311, int(feed['typeid']), feed['key'], *psr.uckeys).tostr()
        else:
            likeid = '%d/%d' % (day_stamp(int(feed["abstime"])), feed["hash"])
        btnLike = telegram.InlineKeyboardButton("Like", callback_data=likeid)
        rpl = telegram.InlineKeyboardMarkup([[btnLike]])

    if int(feed['typeid']) == 5:
        #TODO: forward
        if (forward := psr.parseForward()) is None:
            logger.warning(str(feed["hash"]) + ": cannot parse forward text")
            forward_text = br + "emmm, 没抓到转发消息."
        else:
            forward_nick, forward_link, forward_text = forward
            msg = msg.format(forward=make_link('@' + forward_nick, forward_link)) + br
            msg += '@' + forward_nick + ': '
        msg += forward_text

    img = psr.parseImage()
    if len(img) == 1: msg += br + make_link('P1', img[0])
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
        logger.error(f"{feed['hash']}: {e.message}")

    if len(img) > 1:
        send_photos(bot, chat, img, f'{feed["nickname"]}于{feed["feedstime"]}')


class PollingBot:
    update: Updater
    reload_on_start = False

    def __init__(
        self,
        feedmgr: FeedOperation,
        token: str,
        accept_id,
        method='polling',
        proxy=None
    ):
        self.method = method
        self.accept_id = accept_id
        self.feedmgr = feedmgr

        self.update = Updater(token, use_context=True, request_kwargs=proxy)
        dispatcher = self.update.dispatcher
        dispatcher.add_handler(CommandHandler("start", self.onStart))
        dispatcher.add_handler(CommandHandler("refresh", self.onRefresh))
        dispatcher.add_handler(CallbackQueryHandler(self.like))

    def onRefresh(self, update: telegram.Update, context: CallbackContext):
        logger.debug('Refresh command is called')
        self.chat_id = update.effective_chat.id
        self.onFetch(context.bot, False)

    def onStart(self, update: telegram.Update, context):
        logger.info('Bot starting')
        self.chat_id = update.effective_chat.id
        self.onFetch(context.bot, self.reload_on_start)

    def run(self):
        if self.method == "polling":
            self.polling()
        elif self.method == "webhook":
            raise NotImplementedError("Webhook is not available now.")
        else:
            raise ValueError('%s is invalid starting method' % self.method)

    def polling(self):
        try:
            self.update.start_polling()
        except NetworkError as e:
            logger.error(e.message)
            self.update.stop()
            return
        logger.info("start polling")
        self.update.idle()

    def like(self, update: telegram.Update, context):
        logger.info("like post start")
        query: telegram.CallbackQuery = update.callback_query
        data: str = query.data
        if '/' in data:
            try:
                if not self.feedmgr.likeAFile(data + ".json"):
                    query.answer(text='Failed to send like post.')
                    return
            except FileNotFoundError:
                query.answer(text="该应用消息已超过服务器保留时限或保留上限, 超过时限的应用消息无法点赞.")
                query.edit_message_text(
                    text=query.message.text_html, parse_mode=telegram.ParseMode.HTML
                )
                return
        else:
            if not self.feedmgr.like(LikeId.fromstr(data)):
                query.answer(text='Failed to send like post.')
                return
        query.edit_message_text(
            text=query.message.text_html + br + '❤', parse_mode=telegram.ParseMode.HTML
        )
        logger.info("like post end")

    def onFetch(self, bot: telegram.Bot, reload: bool):
        cmd = "force-refresh" if reload else "refresh"

        if self.chat_id in self.accept_id:
            logger.info("%d: start %s" % (self.chat_id, cmd))
        else:
            logger.info(f"{self.chat_id}: illegal access")
            bot.send_message(
                chat_id=self.chat_id, text="Sorry. But bot won't answer unknown chat."
            )
        try:
            new = self.feedmgr.fetchNewFeeds(reload)
        except TimeoutError:
            bot.send_message(
                chat_id=self.chat_id,
                text="Sorry. But network is always busy. Try later."
            )
            return
        for i in new:
            send_feed(bot, self.chat_id, i)
        bot.send_message(
            chat_id=self.chat_id, text="Done. Fetched %d feeds." % len(new)
        )
        logger.info("%s end" % cmd)

    def sendQR(self, filename: str):
        """Send a QR code pic to the chat

        Args:
            filename (str): qr code path
        """
        with open(filename, 'rb') as f:
            self.update.bot.send_photo(
                chat_id=self.chat_id,
                photo=f,
                caption='Scan the QR code to login.',
            )
