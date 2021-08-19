import logging

import telegram
from qzonebackend.feed import day_stamp
from qzonebackend.qzfeedparser import QZFeedParser as Parser
from telegram.error import BadRequest, NetworkError, TimedOut
from uihook import NullUI

from . import *

br = '\n'
hr = '============================='

logger = logging.getLogger("telegram")


def html_link(txt, link) -> str:
    return f'<a href="{link}">{txt}</a>'


class TgUI(NullUI):
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
            reply_markup=telegram.InlineKeyboardMarkup([[
                telegram.InlineKeyboardButton('refresh', callback_data='qr_refresh'),
            ]]) if self._resend else None
        )

    def QrResend(self):
        self.qr_msg = self.qr_msg.edit_media(
            media=telegram.InputMediaPhoto(
                self._resend(),
                caption='二维码已刷新.',
            ),
            reply_markup=telegram.InlineKeyboardMarkup([[
                telegram.InlineKeyboardButton('refresh', callback_data='qr_refresh')
            ]]) if self._resend else None
        )

    def QrExpired(self, png: bytes):
        self.qr_msg = self.qr_msg.edit_media(
            media=telegram.InputMediaPhoto(
                png,
                caption='二维码已过期, 重新扫描此二维码.',
            ),
            reply_markup=telegram.InlineKeyboardMarkup([[
                telegram.InlineKeyboardButton('refresh', callback_data='qr_refresh')
            ]]) if self._resend else None
        )

    def QrFailed(self, *args, **kwargs):
        if self.qr_msg.delete():
            del self.qr_msg
        self.bot.send_message("😢 扫码无响应")

    def QrScanSucceessed(self):
        if self.qr_msg.delete():
            del self.qr_msg

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

    def fetchEnd(self, succ_num: int, err_num: int):
        if self.ui_msg.delete(): del self.ui_msg
        if succ_num == 0 and err_num == 0:
            cmd = "您已经跟上了时代✔"
        else:
            cmd = f"成功爬取{succ_num}条说说."
            if err_num > 0:
                cmd += f" 发送失败{err_num}条, 重试也没有用( 请检查服务端日志."
        self.bot.send_message(chat_id=self.chat_id, text=cmd)

    def fetchError(self, msg=None):
        if msg is None: msg = 'Ooops\\.\\.\\. 出错了qvq'
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_markdown_v2 + '\n❌ ' + msg,
                parse_mode=telegram.ParseMode.MARKDOWN_V2
            )
            del self.ui_msg
        else:
            self.bot.send_message(
                chat_id=self.chat_id,
                text='❌ ' + msg,
                parse_mode=telegram.ParseMode.MARKDOWN_V2
            )


def send_photos(bot: telegram.Bot, chat, img: list, caption="", reply_markup=None):
    assert 1 < len(img) <= 10
    pic_objs = [telegram.InputMediaPhoto(media=img[0], caption=caption, parse_mode=telegram.ParseMode.HTML)] + \
        [telegram.InputMediaPhoto(i) for i in img[1:]]
    try:
        bot.send_media_group(chat_id=chat, media=pic_objs)
    except BadRequest as e:
        bot.send_message(
            chat_id=chat,
            text=caption + br + '(bot温馨提示: 部分图片好像没发过来?)' + br + html_link('P1', img[0]),
            reply_markup=reply_markup,
        )
        logger.warning(e.message)
    except TimedOut as e:
        logger.warning(e.message)


def send_feed(bot: telegram.Bot, chat, feed: Parser, like_button=True):
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
    elif not like_button:
        rpl = None
    else:
        if feed.appid == 311:
            likeid = feed.getLikeId().tostr()
        else:
            likeid = f'{day_stamp(feed.abstime)}/{feed.hash}'
        btnLike = telegram.InlineKeyboardButton("Like", callback_data=likeid)
        rpl = telegram.InlineKeyboardMarkup([[btnLike]])

    if feed.appid not in (4, 311) or (feed.typeid == 5):
        try:
            forward = feed.parseForward()
        except Exception:
            forward = None
        if (forward) is None:
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
    if len(img) == 1:
        bot.send_photo(
            chat_id=chat,
            photo=img[0],
            caption=msg,
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=rpl
        )
        return

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
        logger.error(f"{feed.hash}: {e.message}", exc_info=True, stack_info=True)

    if len(img) > 1:
        send_photos(bot, chat, img, f'{feed.nickname}于{feed.feedstime}')
