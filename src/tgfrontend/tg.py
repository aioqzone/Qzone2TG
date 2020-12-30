import logging
import time

import telegram
from qzonebackend.feed import *
from qzonebackend.htmlparser import HTMLParser as Parser
from QzoneBackend.qzone import *
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import (CallbackContext, CallbackQueryHandler,
                          CommandHandler, Updater)

from .compress import LikeId

br = '\n'
logger = logging.getLogger("telegram")


def make_link(txt, link)-> str:
    a = '<a href="{link}">{txt}</a>'
    return a.format(txt = txt, link = link)

def send_photos(bot: telegram.Bot, chat, img: list, caption: str = ""):
    for i in range(len(img)):
        try: bot.send_photo(chat_id = chat, photo = img[i], caption = caption.format(i+1), disable_notification = True)
        except BadRequest: 
            bot.send_message(
                chat_id = chat,
                text = caption.format(i+1) + br + '(bot温馨提示: %s好像没发过来?)' % make_link("图片", img[i]), 
                disable_web_page_preview = False, 
                parse_mode = telegram.ParseMode.HTML
            )
        except TimedOut as e:
            logger.warning(e.message)

def send_feed(bot: telegram.Bot, chat, feed: dict):
    msg = feed["nickname"] + feed["feedstime"]
    if int(feed['typeid']) == 5:
        msg += "转发了{forward}的说说:"
    else:
        msg += "发表了说说:"
    msg += br * 2

    psr = Parser(feed["html"])
    msg += psr.parseText()

    if psr.isLike(): 
        msg += br + '❤'
        rpl = None
    else:
        if int(feed["appid"]) == 311:
            likeid = LikeId(311, int(feed['typeid']), feed['key'], psr.unikey(), psr.curkey()).tostr()
        else:
            likeid = '%d/%d' % (day_stamp(int(feed["abstime"])), feed["hash"])
        btnLike = telegram.InlineKeyboardButton(
            "Like", 
            callback_data = likeid
        )
        rpl = telegram.InlineKeyboardMarkup([[btnLike]])

    if int(feed['typeid']) == 5:
        #TODO: forward
        forward = psr.parseForward()
        if forward is None: 
            logger.warning(str(feed["hash"]) + ": cannot parse forward text")
            forward_text = br + "emmm, 没抓到转发消息."
        else:
            forward_nick, forward_link, forward_text = forward
            msg = msg.format(forward = make_link('@' + forward_nick, forward_link)) + br
            msg += '@' + forward_nick + ': '
        msg += forward_text

    img = psr.parseImage()
    if len(img) == 1: msg += br + make_link('P1', img[0])
    elif img: msg += br + "(bot温馨提示: 多图预警x%d)" % len(img)

    try:
        bot.send_message(
            chat_id = chat, text = msg, parse_mode=telegram.ParseMode.HTML, disable_web_page_preview = len(img) != 1,
            reply_markup = rpl
        )
    except TimedOut as e:
        logger.warning(e.message)
    except NetworkError as e:
        logger.error(str(feed["hash"]) + ': ' + e.message)

    if len(img) > 1:
        send_photos(bot, chat, img, '{name}于{time}'.format(name = feed["nickname"],time = feed["feedstime"]) + ': P{:d}')
    
class PollingBot:
    update: Updater

    def __init__(self, feedmgr: FeedOperation, token: str, accept_id, method='polling', proxy=None):
        self.method = method
        self.accept_id = accept_id
        self.feedmgr = feedmgr
        
        self.update = Updater(token, use_context=True, request_kwargs=proxy)
        dispatcher = self.update.dispatcher
        dispatcher.add_handler(CommandHandler("start", lambda u, c: self.onStart(u, c)))
        dispatcher.add_handler(CommandHandler("refresh", lambda u, c: self.onRefresh(u, c)))
        dispatcher.add_handler(CallbackQueryHandler(lambda u, c: self.like(u, c)))

    def onRefresh(self, update: telegram.Update, context: CallbackContext):
        self.onFetch(context.bot, update.effective_chat.id, False)

    def onStart(self, update: telegram.Update, context):
        self.onFetch(context.bot, update.effective_chat.id, True)

    def run(self):
        if self.method == "polling":
            self.polling()
        elif self.method == "webhook":
            raise NotImplementedError("Webhook is not available now.")
        else: 
            raise ValueError('%s is invalid starting method' % self.method)

    def polling(self):
        try: self.update.start_polling()
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
                    query.answer(text = 'Failed to send like post.')
                    return
            except FileNotFoundError:
                query.answer(text = "该应用消息已超过服务器保留时限(%d天), 超过时限的应用消息无法点赞." % self.feedmgr.keepdays)
                query.edit_message_text(text = query.message.text_html, parse_mode=telegram.ParseMode.HTML)
                return
        else:
            if not self.feedmgr.do_like(LikeId.fromstr(data)):
                query.answer(text = 'Failed to send like post.')
                return
        query.edit_message_text(text = query.message.text_html + br + '❤', parse_mode=telegram.ParseMode.HTML)
        logger.info("like post end")
        
    def onFetch(self, bot: telegram.Bot, chat: int, reload: bool):
        cmd = "force-refresh" if reload else "refresh"

        if str(chat) in self.accept_id:
            logger.info("%d: start %s" % (chat, cmd))
        else:
            logger.info("%d: illegal access")
            bot.send_message(chat_id = chat, text = "Sorry. But bot won't answer unknown chat.")
        try: new = self.feedmgr.fetchNewFeeds(reload)
        except TimeoutError: 
            bot.send_message(chat_id = chat, text = "Sorry. But network is always busy. Try later.")
            return
        for i in new: send_feed(bot, chat, i)
        bot.send_message(
            chat_id = chat, 
            text = "Done. Fetched %d feeds." % len(new)
        )
        logger.info("%s end" % cmd)