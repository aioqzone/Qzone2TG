import logging
import time
from HTMLParser import HTMLParser as parser

import telegram
from telegram.error import BadRequest, TimedOut
from telegram.ext import (CallbackContext, CallbackQueryHandler,
                          CommandHandler, Updater)

import QzoneBackend.qzone as qzone
from .compress import LikeId
from QzoneBackend.feed import day_stamp, fetchNewFeeds
from QzoneBackend.feed import like as do_like
from QzoneBackend.feed import likeAFile

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

    psr = parser(feed["html"])
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
    except telegram.error.NetworkError as e:
        logger.error(str(feed["hash"]) + ': ' + e.message)
    except TimedOut as e:
        logger.warning(e.message)

    if len(img) > 1:
        send_photos(bot, chat, img, '{name}于{time}'.format(name = feed["nickname"],time = feed["feedstime"]) + ': P{:d}')
            
def onFetch(bot: telegram.Bot, chat: int, reload: bool):
    cmd = "force-refresh" if reload else "refresh"

    if str(chat) in botConf["accept_id"]:
        logger.info("%d: start %s" % (chat, cmd))
    else:
        logger.info("%d: illegal access")
        bot.send_message(chat_id = chat, text = "Sorry. But bot won't answer unknown chat.")
    try: new = fetchNewFeeds(reload)
    except TimeoutError: 
        bot.send_message(chat_id = chat, text = "Sorry. But network is always busy. Try later.")
        return
    for i in new: send_feed(bot, chat, i)
    bot.send_message(
        chat_id = chat, 
        text = "Done. Fetched %d feeds." % len(new)
    )
    logger.info("%s end" % cmd)

def refresh(update: telegram.Update, context: CallbackContext):
    onFetch(context.bot, update.effective_chat.id, False)

def start(update: telegram.Update, context):
    onFetch(context.bot, update.effective_chat.id, True)
    
def like(update: telegram.Update, context):
    logger.info("like post start")
    query: telegram.CallbackQuery = update.callback_query
    data: str = query.data
    if '/' in data:
        try:
            if not likeAFile(data + ".json"): 
                query.answer(text = 'Failed to send like post.')
                return
        except FileNotFoundError:
            from config import feed as fConf
            query.answer(text = "该应用消息已超过服务器保留时限(%d天), 超过时限的应用消息无法点赞." % fConf['keepdays'])
            query.edit_message_text(text = query.message.text_html, parse_mode=telegram.ParseMode.HTML)
            return
    else:
        if not do_like(LikeId.fromstr(data)):
            query.answer(text = 'Failed to send like post.')
            return
    query.edit_message_text(text = query.message.text_html + br + '❤', parse_mode=telegram.ParseMode.HTML)
    logger.info("like post end")
    
class PollingBot:
    update: Updater

    def __init__(self, token: str):
        self.update = Updater(token, use_context=True, request_kwargs=botConf.get('proxy', None))
        dispatcher = self.update.dispatcher
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("refresh", refresh))
        dispatcher.add_handler(CallbackQueryHandler(like))

    def start(self):
        if botConf["method"] == "polling":
            self.polling()
        elif botConf["method"] == "webhook":
            raise NotImplementedError("Webhook is not available now.")

    def polling(self):
        try: self.update.start_polling()
        except telegram.error.NetworkError as e:
            logger.error(e.message)
            self.update.stop()
            return
        logger.info("start polling")
        self.update.idle()

PollingBot(botConf["token"]).start()
