from __future__ import annotations

import asyncio
from time import time
from typing import TYPE_CHECKING

from aioqzone.event import QREvent, UPEvent
from aioqzone_feed.event import FeedEvent, HeartbeatEvent
from qqqr.event import sub_of

from qzone3tg.bot.queue import QueueEvent

from ..storage import StorageEvent

if TYPE_CHECKING:
    from aioqzone.type.resp import FeedRep
    from aioqzone_feed.type import FeedContent
    from sqlalchemy.ext.asyncio import AsyncSession
    from telegram import InlineKeyboardMarkup

    from . import BaseApp


@sub_of(QREvent)
def qrevent_hook(_self: BaseApp, base: type[QREvent]):
    from telegram import InputMediaPhoto, Message

    class baseapp_qrevent(base):
        async def LoginFailed(self, meth, msg: str | None = None):
            await super().LoginFailed(meth, msg)
            _self.loginman.suppress_qr_till = time() + _self.loginman.qr_suppress_sec
            await self._cleanup()
            pmsg = f": {msg}" if msg else ""
            await _self.bot.send_message(_self.admin, "二维码登录失败" + pmsg)

        async def LoginSuccess(self, meth):
            await super().LoginSuccess(meth)
            _self.loginman.suppress_qr_till = time() + _self.loginman.qr_suppress_sec
            await _self.restart_heartbeat()
            await self._cleanup()
            await _self.bot.send_message(_self.admin, "登录成功")

        def qr_markup(self) -> InlineKeyboardMarkup | None:
            return

        async def QrFetched(self, png: bytes, times: int):
            context: dict = _self.app.bot_data

            if context.get("qr_msg") is None:
                context["qr_msg"] = await _self.bot.send_photo(
                    _self.admin,
                    png,
                    "扫码登陆:",
                    disable_notification=False,
                    reply_markup=self.qr_markup(),
                )
            else:
                text = f"二维码已过期, 请重新扫描[{times}]"
                if context.get("qr_renew"):
                    text = "二维码已刷新："
                    context["qr_renew"] = False

                msg = await _self.bot.edit_message_media(
                    InputMediaPhoto(png, text),
                    _self.admin,
                    context["qr_msg"].message_id,
                    reply_markup=self.qr_markup(),
                )
                if isinstance(msg, Message):
                    context["qr_msg"] = msg

        async def _cleanup(self):
            context: dict = _self.app.bot_data
            context["qr_renew"] = False

            if isinstance(context.get("qr_msg"), Message):
                try:
                    await context["qr_msg"].delete()
                except BaseException as e:
                    _self.log.warning(e)
                finally:
                    self.qr_msg = None

    return baseapp_qrevent


@sub_of(UPEvent)
def upevent_hook(_self: BaseApp, base: type[UPEvent]):
    from telegram import ForceReply, Message

    class baseapp_upevent(base):
        async def LoginFailed(self, meth, msg: str | None = None):
            await super().LoginFailed(meth, msg)
            _self.loginman.suppress_up_till = time() + _self.loginman.up_suppress_sec
            pmsg = f": {msg}" if msg else ""
            await _self.bot.send_message(_self.admin, "密码登录失败" + pmsg)

        async def LoginSuccess(self, meth):
            await super().LoginSuccess(meth)
            await _self.restart_heartbeat()
            await _self.bot.send_message(_self.admin, "登录成功", disable_notification=True)

        async def GetSmsCode(self, phone: str, nickname: str) -> str | None:
            m = await _self.bot.send_message(
                _self.admin,
                f"将要登录的是{nickname}，请输入密保手机({phone})上收到的验证码:",
                disable_notification=False,
                reply_markup=ForceReply(input_field_placeholder="012345"),
            )
            code = await self.force_reply_answer(m)
            if code is None:
                await _self.bot.send_message(_self.admin, "超时未回复")
                await m.edit_reply_markup(reply_markup=None)
                return

            if len(code) != 6:
                await _self.bot.send_message(_self.admin, "应回复六位数字验证码")
                await m.edit_reply_markup(reply_markup=None)
                return
            return code

        async def force_reply_answer(self, msg: Message) -> str | None:
            """A hook cannot get answer from the user. This should be done by handler in app.
            So this method should be implemented in app level.

            :param msg: The force reply message to wait for the reply from user.
            :param timeout: wait timeout
            :return: None if timeout, else the reply string.
            """
            return

    return baseapp_upevent


@sub_of(FeedEvent)
def feedevent_hook(_self: BaseApp, base: type[FeedEvent]):
    from ..storage.orm import FeedOrm

    class baseapp_feedevent(base):
        def __init__(self) -> None:
            super().__init__()

            self.block = set(_self.conf.qzone.block or ())
            if _self.conf.qzone.block_self:
                self.block.add(_self.conf.qzone.uin)

        async def FeedProcEnd(self, bid: int, feed: FeedContent):
            _self.log.debug(f"bid={bid}: {feed}")
            if feed.uin in self.block:
                _self.log.info(f"Blocklist hit: {feed.uin}({feed.nickname})")
                return await self.FeedDropped(bid, feed)
            await _self.queue.add(bid, feed)

        async def FeedDropped(self, bid: int, feed):
            _self.log.debug(f"batch {bid}: one feed dropped")
            _self.queue.skip_num += 1

        async def FeedMediaUpdate(self, bid: int, feed: FeedContent):
            _self.log.debug(f"feed update received: media={feed.media}")
            await _self.queue.edit(bid, feed)

        async def StopFeedFetch(self, feed: FeedRep) -> bool:
            return await _self.store.exists(*FeedOrm.primkey(feed))

    return baseapp_feedevent


@sub_of(HeartbeatEvent)
def heartbeatevent_hook(_self: BaseApp, base: type[HeartbeatEvent]):
    from aioqzone.event import LoginMethod

    class baseapp_heartbeatevent(base):
        async def HeartbeatFailed(self, exc: BaseException | None = None):
            _self.log.debug(f"heartbeat failed: {exc}")
            lm = _self.loginman
            qr_avil = LoginMethod.qr in lm.order and not lm.qr_suppressed
            up_avil = LoginMethod.up in lm.order and not lm.up_suppressed
            if qr_avil or up_avil:
                try:
                    await _self.loginman.new_cookie()
                except:
                    return
                else:
                    await _self.restart_heartbeat()
                return

            _self.log.warning("All login methods suppressed and heartbeat failed.")

            info = f"({exc})" if exc else ""
            await _self.bot.send_message(_self.admin, "由于距上次登录的时间间隔少于您所指定的最小值，自动登录已暂停。" + info)

        async def HeartbeatRefresh(self, num: int):
            _self.log.info(f"Heartbeat triggers a refresh: count={num}")
            if _self._tasks["fetch"]:
                _self.log.warning(
                    "fetch taskset should contain only one task, heartbeat fetch skipped."
                )
                _self.log.debug(_self._tasks["fetch"])
                return
            _self.add_hook_ref("fetch", _self._fetch(_self.conf.bot.admin, is_period=True))

    return baseapp_heartbeatevent


@sub_of(QueueEvent)
def queueevent_hook(_self: BaseApp, base: type[QueueEvent]):
    from aioqzone_feed.type import BaseFeed
    from sqlalchemy import select

    from ..storage.orm import FeedOrm, MessageOrm

    class baseapp_queueevent(base):
        @property
        def sess(self):
            return _self.store.sess

        async def _update_message_ids(
            self,
            feed: BaseFeed,
            mids: list[int] | None,
            sess: AsyncSession | None = None,
            flush: bool = True,
        ):
            if sess is None:
                async with self.sess() as newsess:
                    await self._update_message_ids(feed, mids, sess=newsess, flush=flush)
                return

            if flush:
                await self._update_message_ids(feed, mids, sess=sess, flush=False)
                await sess.commit()
                return

            # query existing mids
            stmt = select(MessageOrm)
            stmt = stmt.where(*MessageOrm.fkey(feed))
            result = await sess.scalars(stmt)

            # delete existing mids
            tasks = [asyncio.create_task(sess.delete(i)) for i in result]
            if tasks:
                await asyncio.wait(tasks)

            if mids is None:
                return
            for mid in mids:
                sess.add(MessageOrm(uin=feed.uin, abstime=feed.abstime, mid=mid))

        async def SaveFeed(self, feed: BaseFeed, mids: list[int] | None = None):
            """Add/Update an record by the given feed and messages id.

            :param feed: feed
            :param mids: message id list, defaults to None
            """

            async def _update_feed(feed, sess: AsyncSession):
                prev = await _self.store.get_feed_orm(*FeedOrm.primkey(feed), sess=sess)
                if prev:
                    # if exist: update
                    FeedOrm.set_by(prev, feed)
                else:
                    # not exist: add
                    sess.add(FeedOrm.from_base(feed))

            async with self.sess() as sess:
                async with sess.begin():
                    # BUG: asyncio.wait/gather raises error at the end of a transaction
                    await self._update_message_ids(feed, mids, sess=sess, flush=False)
                    await _update_feed(feed, sess=sess)

        async def GetMid(self, feed: BaseFeed) -> list[int]:
            r = await _self.store.get_msg_orms(*MessageOrm.fkey(feed))
            return [i.mid for i in r]

    return baseapp_queueevent


@sub_of(StorageEvent)
def storageevent_hook(_self: BaseApp, base: type[StorageEvent]):
    from aioqzone_feed.type import BaseFeed

    from ..storage.orm import FeedOrm, MessageOrm

    class baseapp_storageevent(base):
        @property
        def sess(self):
            return _self.store.sess

        async def Mid2Feed(self, mid: int) -> BaseFeed | None:
            mo = await _self.store.get_msg_orms(MessageOrm.mid == mid)
            if not mo:
                return
            orm = await _self.store.get_feed_orm(
                FeedOrm.uin == mo[0].uin, FeedOrm.abstime == mo[0].abstime
            )
            if orm is None:
                return
            return BaseFeed.from_orm(orm)

        async def Clean(self, seconds: float):
            return await _self.store.clean(seconds)

    return baseapp_storageevent
