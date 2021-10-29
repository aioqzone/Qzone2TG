import logging
from typing import Callable, List

import telegram
from qzone2tg.middleware import ContentExtracter
from qzone2tg.middleware.hook import NullUI
from qzone2tg.utils.decorator import Retry
from telegram.error import BadRequest, TimedOut

from .compress import LikeId
from .utils import FixUserBot

SUPPORT_TYPEID = (0, 2, 5)
SUPPORT_APPID = (4, 11, 202, 311)
APP_NAME = {4: 'QQ相册', 202: '分享', 311: 'QQ空间'}

br = '\n'          # tg donot support <br>, instead \n is used
hr = '=========================='

logger = logging.getLogger(__name__)


class retry_once(Retry):
    def __init__(self, msg_callback=None, **kw):
        self.msg_callback = msg_callback or (lambda exc: str(exc))
        super().__init__({
            TimedOut: self.__TimedOut__,
            BadRequest: self.__BadRequest__,
            BaseException: self.__BaseException__
        }, **kw)

    def _last_fail(self, e: BaseException):
        logger.error(self.msg_callback(exc=e) + " (retry failed)")

    def __TimedOut__(self, e: TimedOut, i: int):
        if i < 1:
            logger.warning(e.message)
        else:
            self._last_fail(e)

    def __BadRequest__(self, e: BadRequest, i: int):
        if i < 1:
            logger.warning(self.msg_callback(exc=e), exc_info=True)
        else:
            self._last_fail(e)

    def __BaseException__(self, e: BaseException, i: int):
        if i < 1:
            logger.error(self.msg_callback(exc=e), exc_info=True)
        else:
            self._last_fail(e)


class TgUI(NullUI):
    def __init__(
        self,
        bot,
        chat_id: int = None,
        times_per_second: int = None,
        disable_notification: bool = False
    ) -> None:
        super().__init__()
        self.bot = FixUserBot(
            bot,
            chat_id,
            telegram.ParseMode.HTML,
            times_per_second=times_per_second,
            disable_notification=disable_notification
        )

    def register_sendfeed_callback(self, send_cb: Callable):
        self.sendfeed_callback = send_cb

    def _defaultButton(self):
        return telegram.InlineKeyboardMarkup([[
            telegram.InlineKeyboardButton('refresh', callback_data='qr_refresh'),
            telegram.InlineKeyboardButton('cancel', callback_data='qr_cancel'),
        ]])

    def QrFetched(self, png: bytes):
        self.qr_msg = self.bot.sendMedia(
            '扫码登陆:', png, self._resend and self._defaultButton()
        )[0]

    def QrResend(self):
        self.qr_msg = self.qr_msg.edit_media(
            media=telegram.InputMediaPhoto(
                self._resend(),
                caption='二维码已刷新.',
            ),
            reply_markup=self._resend and self._defaultButton()
        )

    def QrCanceled(self):
        if self.qr_msg.delete():
            del self.qr_msg
        self.bot.sendMessage('二维码登录已取消, 当前任务终止.')

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
        self.bot.sendMessage("😢 扫码无响应")

    def QrScanSucceessed(self):
        if self.qr_msg.delete():
            del self.qr_msg

    def loginSuccessed(self):
        self.ui_msg = self.bot.sendMessage('✔ 登录成功')[0]

    def loginFailed(self, msg: str = "unknown"):
        self.bot.sendMessage(f'❌ 登录失败: <b>{msg}</b>')

    def pageFetched(self, msg):
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_html + br + '✔ ' + msg,
                parse_mode=telegram.ParseMode.HTML
            )
        else:
            self.ui_msg = self.bot.sendMessage(text='✔ ' + msg)[0]

    def fetchEnd(self, succ_num: int, err_num: int, silent=False):
        if hasattr(self, 'ui_msg') and self.ui_msg.delete():
            del self.ui_msg
        if succ_num == 0 and err_num == 0 and not silent:
            cmd = "您已经跟上了时代✔"
        else:
            cmd = f"成功发送{succ_num}条说说."
            if err_num > 0:
                cmd += f" 发送失败{err_num}条, 重试也没有用( 请检查服务端日志."
        if not silent:
            self.bot.sendMessage(cmd)

    def fetchError(self, msg=None):
        if msg is None: msg = 'Ooops... 出错了qvq'
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_html + '\n❌ ' + msg,
                parse_mode=telegram.ParseMode.HTML
            )
            del self.ui_msg
        else:
            self.bot.sendMessage('❌ ' + msg)

    def contentReady(self, msg: str, media: List[str], reply_markup=None):
        if media:
            return self.bot.sendMedia(msg, media, reply_markup)
        else:
            return self.bot.sendMessage(msg, reply_markup)

    def mediaUpdate(self, msg_objs: List[telegram.Message], media: List[str]):
        msg_objs = [i for i in msg_objs if i.photo or i.video]

        assert len(msg_objs) == len(media)
        logger.info(f'updating {len(msg_objs)} images')

        return [self.bot.editMedia(m, u) for m, u in zip(msg_objs, media)]

    def feedFetched(self, feed):
        return self.sendfeed_callback(feed)


class TgExtracter(ContentExtracter):
    def __init__(self, feed, uin: int) -> None:
        super().__init__(feed)
        self.uin = uin

    @staticmethod
    def html_link(txt, link) -> str:
        return f'<a href="{link}">{txt}</a>' if link else txt

    def msg(self):
        if self.feed.appid not in SUPPORT_APPID: return ''
        if self.feed.typeid not in SUPPORT_TYPEID:
            logger.warning(f'Unsupported typeid={self.feed.typeid}')

        msg = self.feed.nickname + self.feed.feedstime

        is_forward = self.feed.typeid == 5
        has_text = bool(text := self.feed.parseText())

        if is_forward:
            msg += "转发了{forward}的说说:"
        else:
            msg += "发表了说说:"

        if has_text:
            msg += br * 2
            msg += text

        if self.feed.isLike:
            if has_text: msg += br * 2
            msg += '❤'

        if is_forward or self.feed.appid not in (4, 311):
            try:
                forward = self.feed.parseForward()
            except Exception:
                forward = None
            if forward is None:
                logger.warning(
                    f"{self.feed}: cannot parse forward text. appid={self.feed.appid}, typeid={self.feed.typeid}"
                )
                msg = msg.format(forward=APP_NAME[self.feed.appid])
            else:
                forward_nick, forward_link, forward_text = forward
                html_forwardee = self.html_link(
                    '@' + (forward_nick or APP_NAME[self.feed.appid]), forward_link
                )
                msg = msg.format(forward=html_forwardee) + br
                msg += hr + br
                if forward_nick: msg += html_forwardee + ': '
                msg += forward_text
        return msg

    def forward(self):
        pass

    def likeButton(self):
        if self.feed.isLike: return
        likeid = None
        if self.feed.appid == 311:
            likeid = LikeId(**self.feed.getLikeId()).tostr()
        if likeid is None:
            likeid = '/' + self.feed.fid
        btnLike = telegram.InlineKeyboardButton("Like", callback_data=likeid)
        return telegram.InlineKeyboardMarkup([[btnLike]])

    def content(self):
        return self.msg(), self.img() + self.video()

    @property
    def isBlocked(self):
        return self.feed.uin == self.uin
