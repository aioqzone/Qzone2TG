from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aioqzone.event import UPEvent
from aioqzone_feed.event import FeedEvent, HeartbeatEvent
from qqqr.event import sub_of

if TYPE_CHECKING:
    from . import InteractApp


@sub_of(UPEvent)
def upevent_hook(_self: InteractApp, base: type[UPEvent]):
    from telegram import Message, Update
    from telegram.ext import MessageHandler, filters

    class ReplyHandler(MessageHandler):
        def __init__(self, filters, callback, reply: Message):
            super().__init__(filters, callback)
            self.reply = reply

        def check_update(self, update: Update):
            if super().check_update(update) is False:
                return False
            msg = update.effective_message
            assert msg

            if msg.reply_to_message and msg.reply_to_message.message_id == self.reply.message_id:
                return
            return False

    class interactapp_upevent(base):
        async def force_reply_answer(self, msg) -> str | None:
            code = ""
            evt = asyncio.Event()

            def cb(update: Update, _):
                nonlocal code
                assert update.effective_message
                code = update.effective_message.text or ""
                code = code.strip()
                evt.set()

            handler = ReplyHandler(filters.Regex(r"^\s*\d{6}\s*$"), cb, msg)
            _self.app.add_handler(handler)

            try:
                await asyncio.wait_for(evt.wait(), timeout=_self.conf.qzone.vcode_timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return
            else:
                return code
            finally:
                _self.app.remove_handler(handler)

    return interactapp_upevent


@sub_of(HeartbeatEvent)
def heartbeatevent_hook(_self: InteractApp, base: type[HeartbeatEvent]):
    from aioqzone.event import LoginMethod

    class interactapp_heartbeatevent(base):
        async def HeartbeatRefresh(self, num: int):
            if _self.fetch_lock.locked:
                _self.log.warning("Heartbeat refresh skipped since fetch is running.")
                return
            await super().HeartbeatRefresh(num)

            tasks = [t for t in _self._tasks["fetch"] if t._state == "PENDING"]
            match len(tasks):
                case n if n > 1:
                    task = next(filter(lambda t: t._state == "PENDING", tasks))
                    _self.log.warn(
                        "fetch taskset should contain only one task, the first pending task is used."
                    )
                case n if n == 1:
                    task = next(iter(tasks))
                case _:
                    _self.log.warn("fetch task not found, fetch lock skipped.")
                    return

            _self.fetch_lock.acquire(task)

        async def HeartbeatFailed(self, exc: BaseException | None):
            await super().HeartbeatFailed(exc)
            lm = _self.loginman
            qr_avil = LoginMethod.qr in lm.order and not lm.qr_suppressed
            up_avil = LoginMethod.up in lm.order and not lm.up_suppressed
            if qr_avil or up_avil:
                await _self.bot.send_message(
                    _self.admin, "/relogin 重新登陆，/help 查看帮助", disable_notification=True
                )

    return interactapp_heartbeatevent


@sub_of(FeedEvent)
def feedevent_hook(_self: InteractApp, base: type[FeedEvent]):
    from aioqzone_feed.type import FeedContent

    class interactapp_feedevent(base):
        async def FeedProcEnd(self, bid: int, feed: FeedContent):
            if await _self.blockset.contains(feed.uin):
                await self.FeedDropped(bid, feed)
                return
            await self.FeedProcEnd(bid, feed)

    return interactapp_feedevent
