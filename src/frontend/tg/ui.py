import logging
from functools import wraps

import telegram
from middleware import ContentExtracter
from middleware.uihook import NullUI
from telegram.error import BadRequest, TimedOut
from .compress import LikeId

SUPPORT_TYPEID = (0, 5)
SUPPORT_APPID = (4, 202, 311)
APP_NAME = {4: 'QQ相册', 202: '微信', 311: 'QQ空间'}

br = '\n'
hr = '============================='

logger = logging.getLogger(__name__)


def retry_once(func, msg_callback=None):
    log_kw = dict(exc_info=True, stack_info=True, stacklevel=2)

    @wraps(func)
    def retry_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TimedOut as e:
            logger.warning(e.message)
        except BadRequest as e:
            logger.warning(
                msg_callback(*args, exc=e, **kwargs) if msg_callback else str(e),
                **log_kw
            )
        except Exception as e:
            logger.error(
                msg_callback(*args, exc=e, **kwargs) if msg_callback else str(e),
                **log_kw
            )

        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(
                (msg_callback(*args, exc=e, **kwargs) if msg_callback else str(e)) +
                " (retry failed)"
            )

    return retry_wrapper


class TgUI(NullUI):
    bot: telegram.Bot
    chat_id: int

    def __init__(self, bot, chat_id=None) -> None:
        super().__init__()
        self.bot = bot
        if chat_id is not None: self.chat_id = chat_id

    def _defaultButton(self):
        return telegram.InlineKeyboardMarkup([[
            telegram.InlineKeyboardButton('refresh', callback_data='qr_refresh'),
            telegram.InlineKeyboardButton('cancel', callback_data='qr_cancel'),
        ]])

    def QrFetched(self, png: bytes):
        self.qr_msg = self.bot.send_photo(
            chat_id=self.chat_id,
            photo=png,
            caption='扫码登陆.',
            reply_markup=self._defaultButton() if self._resend else None
        )

    def QrResend(self):
        self.qr_msg = self.qr_msg.edit_media(
            media=telegram.InputMediaPhoto(
                self._resend(),
                caption='二维码已刷新.',
            ),
            reply_markup=self._defaultButton() if self._resend else None
        )

    def QrCanceled(self):
        if self.qr_msg.delete():
            del self.qr_msg
        self.bot.send_message(chat_id=self.chat_id, text='二维码登录已取消, 当前任务终止.')

    def QrExpired(self, png: bytes):
        self.qr_msg = self.qr_msg.edit_media(
            media=telegram.InputMediaPhoto(
                png,
                caption='二维码已过期, 重新扫描此二维码.',
            ),
            reply_markup=self._defaultButton() if self._resend else None
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

    def loginFailed(self, msg: str = "unknown"):
        self.bot.send_message(
            chat_id=self.chat_id,
            text=f'❌ 登录失败: <b>{msg}</b>',
            parse_mode=telegram.ParseMode.HTML
        )

    def pageFetched(self, msg):
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_html + br + '✔ ' + msg,
                parse_mode=telegram.ParseMode.HTML
            )
        else:
            self.ui_msg = self.bot.send_message(
                chat_id=self.chat_id,
                text='✔ ' + msg,
                parse_mode=telegram.ParseMode.HTML
            )

    def fetchEnd(self, succ_num: int, err_num: int):
        if hasattr(self, 'ui_msg') and self.ui_msg.delete():
            del self.ui_msg
        if succ_num == 0 and err_num == 0:
            cmd = "您已经跟上了时代✔"
        else:
            cmd = f"成功爬取{succ_num}条说说."
            if err_num > 0:
                cmd += f" 发送失败{err_num}条, 重试也没有用( 请检查服务端日志."
        self.bot.send_message(chat_id=self.chat_id, text=cmd)

    def fetchError(self, msg=None):
        if msg is None: msg = 'Ooops... 出错了qvq'
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_html + '\n❌ ' + msg,
                parse_mode=telegram.ParseMode.HTML
            )
            del self.ui_msg
        else:
            self.bot.send_message(
                chat_id=self.chat_id,
                text='❌ ' + msg,
                parse_mode=telegram.ParseMode.HTML
            )

    def contentReady(self, msg: str, img: list, reply_markup=None):
        if not img:
            return self.bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                parse_mode=telegram.ParseMode.HTML,
                reply_markup=reply_markup
            )
        elif len(img) == 1:
            return self.bot.send_photo(
                chat_id=self.chat_id,
                caption=msg,
                photo=img[0],
                parse_mode=telegram.ParseMode.HTML,
                reply_markup=reply_markup
            )
        elif reply_markup:
            return [self.contentReady(msg, None, reply_markup)
                    ] + self.contentReady(None, img)
        else:
            return self.bot.send_media_group(
                chat_id=self.chat_id,
                media=[telegram.InputMediaPhoto(media=img[0], caption=msg, parse_mode=telegram.ParseMode.HTML)] + \
                    [telegram.InputMediaPhoto(i) for i in img[1:]]
            )


class TgExtracter(ContentExtracter):
    def __init__(self, feed, uin: int) -> None:
        super().__init__(feed)
        self.uin = uin

    @staticmethod
    def html_link(txt, link) -> str:
        return f'<a href="{link}">{txt}</a>'

    def msg(self):
        if self.feed.appid not in SUPPORT_APPID: return
        if self.feed.typeid not in SUPPORT_TYPEID: return

        msg = self.feed.nickname + self.feed.feedstime

        if self.feed.typeid == 5:
            msg += "转发了{forward}的说说:"
        else:
            msg += "发表了说说:"
        msg += br * 2
        msg += self.feed.parseText()

        if self.feed.isLike:
            msg += br + br + '❤'

        if self.feed.appid not in (4, 311) or (self.feed.typeid == 5):
            try:
                forward = self.feed.parseForward()
            except Exception:
                forward = None
            if (forward) is None:
                logger.warning(
                    f"{self.feed.hash}: cannot parse forward text. appid={self.feed.appid}, typeid={self.feed.typeid}"
                )
                msg = msg.format(forward=APP_NAME[self.feed.appid])
            else:
                forward_nick, forward_link, forward_text = forward
                msg = msg.format(
                    forward=self.html_link('@' + forward_nick, forward_link)
                ) + br
                msg += hr + br
                msg += '@' + forward_nick + ': '
                msg += forward_text
        return msg

    def forward(self):
        pass

    def likeButton(self):
        if self.feed.isLike: return
        if self.feed.appid == 311:
            likeid = LikeId(**self.feed.getLikeId()).tostr()
        else:
            likeid = '/' + self.feed.fid
        btnLike = telegram.InlineKeyboardButton("Like", callback_data=likeid)
        return telegram.InlineKeyboardMarkup([[btnLike]])

    def content(self):
        return self.msg(), self.img()

    @property
    def isBlocked(self):
        return self.feed.uin == self.uin
