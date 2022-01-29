"""Inherits all hooks from aioqzone and implements hook behavior."""

from aioqzone.interface.hook import LoginEvent, QREvent
from aioqzone_feed.interface.hook import FeedContent, FeedEvent
from telegram import Bot

class UnifiedHook(LoginEvent, QREvent, FeedEvent):
    def __init__(self, bot) -> None:
        super().__init__()

    async def LoginFailed(self, msg: str = None):
        return await super().LoginFailed(msg)

    async def LoginSuccess(self):
        return await super().LoginSuccess()

    async def QrFetched(self, png: bytes, renew: bool = False):
        return await super().QrFetched(png, renew)

    async def QrFailed(self, msg: str = None):
        return await super().QrFailed(msg)

    async def QrSucceess(self):
        return await super().QrSucceess()

    async def FeedProcEnd(self, bid: int, feed: FeedContent):
        return await super().FeedProcEnd(bid, feed)

    async def FeedMediaUpdate(self, feed: FeedContent):
        return await super().FeedMediaUpdate(feed)
