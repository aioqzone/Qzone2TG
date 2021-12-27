import logging
from typing import Callable, List

import telegram
from qzone2tg.middleware import ContentExtracter
from qzone2tg.middleware.hook import NullUI

from .compress import LikeId
from .utils import FixUserBot

SUPPORT_TYPEID = (0, 2, 5, 11)
SUPPORT_APPID = (4, 11, 202, 311)
APP_NAME = {4: 'QQ相册', 202: '分享', 311: 'QQ空间'}

br = '\n'    # tg donot support <br>, instead \n is used
hr = '=========================='

logger = logging.getLogger(__name__)


class TgExtracter(ContentExtracter):
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
        return super().isBlocked


class TgUI(NullUI):
    def __init__(
        self,
        bot,
        chat_id: int,
        times_per_second: int = None,
    ) -> None:
        super().__init__()
        self.bot = FixUserBot(
            bot,
            chat_id,
            times_per_second=times_per_second,
        )
        self.queue = {}

    def _defaultButton(self):
        return telegram.InlineKeyboardMarkup([[
            telegram.InlineKeyboardButton('refresh', callback_data='qr_refresh'),
            telegram.InlineKeyboardButton('cancel', callback_data='qr_cancel'),
        ]])

    def QrFetched(self, png: bytes):
        self.qr_msg = self.bot.sendMedia(
            '扫码登陆:', [png], self._resend and self._defaultButton(), disable_notification=False
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
        super().QrCanceled()
        if self.qr_msg.delete():
            del self.qr_msg
        self.bot.sendMessage('二维码登录已取消, 当前任务终止.', disable_notification=True)

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
        self.bot.sendMessage("😢 扫码无响应", disable_notification=True)
        # Assuming the user is sleeping... I guess disable notification is better :D

    def QrScanSucceessed(self):
        if self.qr_msg.delete():
            del self.qr_msg

    def loginSuccessed(self):
        self.ui_msg = self.bot.sendMessage('✔ 登录成功', disable_notification=True)[0]

    def loginFailed(self, msg: str = "unknown"):
        self.bot.sendMessage(f'❌ 登录失败: <b>{msg}</b>')

    def pageFetched(self, msg):
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_html + br + '✔ ' + msg, parse_mode=telegram.ParseMode.HTML
            )
        else:
            self.ui_msg = self.bot.sendMessage(text='✔ ' + msg, disable_notification=True)[0]

    def _fetchEnd(self, sum: int, err: int, silent=False):
        assert sum >= err
        if hasattr(self, 'ui_msg') and self.ui_msg.delete():
            del self.ui_msg
        if sum == 0 and not silent:
            cmd = "您已经跟上了时代✔"
        else:
            cmd = f"成功发送{sum - err}条说说."
            if err > 0:
                cmd += f" 发送失败{err}条, 重试也没有用( 请检查服务端日志."
        if not silent:
            self.bot.sendMessage(cmd, disable_notification=True)

    def fetchError(self, msg=None):
        if msg is None: msg = 'Ooops... 出错了qvq'
        if hasattr(self, 'ui_msg'):
            self.ui_msg = self.ui_msg.edit_text(
                self.ui_msg.text_html + '\n❌ ' + msg, parse_mode=telegram.ParseMode.HTML
            )
            del self.ui_msg
        else:
            self.bot.sendMessage('❌ ' + msg)

    def updateMedia(self, msg_objs: List[telegram.Message], media: List[str]):
        msg_objs = [i for i in msg_objs if i.photo or i.video]

        if len(msg_objs) < len(media):
            logger.warning(f'media more than message: {len(media)} > {len(msg_objs)}')
        elif len(msg_objs) > len(media):
            logger.error(f'media less than message: {len(media)} < {len(msg_objs)}')

        logger.info(f'updating {min(len(media), len(msg_objs))} images')

        return [self.bot.editMedia(m, u) for m, u in zip(msg_objs, media)]
