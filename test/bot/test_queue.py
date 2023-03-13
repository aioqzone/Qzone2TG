from collections import defaultdict
from typing import cast
from unittest.mock import patch

import pytest
from aioqzone.type.internal import PersudoCurkey
from aioqzone_feed.type import FeedContent
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html
from telegram import Bot
from telegram.error import BadRequest, TimedOut

from qzone3tg.bot.queue import MsgQueue, QueueEvent
from qzone3tg.bot.splitter import FetchSplitter
from qzone3tg.type import FeedPair

from . import FakeBot, fake_feed, fake_media

pytestmark = pytest.mark.asyncio


class Ihave0(QueueEvent):
    async def GetMid(self, feed: FeedContent) -> list[int] | None:
        if feed.entities[0].con == "0":  # type: ignore
            return [0]

    async def reply_markup(self, feed, need_forward: bool):
        return FeedPair(1, 1 if need_forward else None)


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture
def queue(client: ClientAdapter, fake_bot: Bot):
    q = MsgQueue(fake_bot, FetchSplitter(client), defaultdict(int))
    q.register_hook(Ihave0())
    return q


class TestQueue:
    async def test_add(self, queue: MsgQueue):
        queue.new_batch(0)
        f = fake_feed(0)
        queue.add(0, f)
        assert len(queue.q) == 1
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert isinstance(queue.q[f], FeedPair)
        assert queue.q[f].feed

        queue.add(1, f)
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert len(queue.q) == 1
        f = fake_feed(1)
        f.uin = 1
        queue.add(0, f)
        assert len(queue.q) == 2
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert isinstance(queue.q[f], FeedPair)
        assert queue.q[f].feed

    async def test_send_norm(self, queue: MsgQueue):
        queue.new_batch(1)
        for i in range(3):
            f = fake_feed(i + 1)
            f.abstime = i * 1000
            queue.add(1, f)
        await queue.send_all()
        assert queue.sending is None
        bot = cast(FakeBot, queue.bot)
        assert len(bot.log) == 3
        assert "".join(i[2][-1] for i in bot.log) == "123"

    async def test_drop_dup_feed(self, queue: MsgQueue):
        queue.new_batch(3)

        f = fake_feed(1)
        queue.add(3, f)

        f = fake_feed(1)
        f.abstime = 1
        queue.add(3, f)

        f = fake_feed(1)
        f.uin = f.abstime = 2
        queue.add(3, f)

        f = fake_feed(1)
        f.abstime = 3
        queue.add(3, f)

        await queue.send_all()
        bot = cast(FakeBot, queue.bot)
        assert len(bot.log) == 2

        assert sum((i.feed for i in queue.q.values()), []) == [1, 1, 2, 1]

    async def test_reply_markup(self, queue: MsgQueue):
        queue.new_batch(2)
        f = fake_feed(2)
        f.forward = fake_feed(1)
        queue.add(2, f)
        await queue.send_all()
        assert queue.sending is None
        bot = cast(FakeBot, queue.bot)
        dfw = bot.log[0][-1]
        dfe = bot.log[1][-1]
        assert dfw["reply_markup"] == 1
        assert dfe["reply_markup"] == 1

    @pytest.mark.parametrize(
        ["exc2r", "grp_len"],
        [
            (TimedOut, 2),
            (BadRequest(""), 2),
            (RuntimeError, 1),
        ],
    )
    async def test_send_retry(self, queue: MsgQueue, exc2r: Exception, grp_len: int):
        queue.new_batch(0)
        with patch.object(FakeBot, "send_photo", side_effect=exc2r):
            f = fake_feed(1)
            f.media = [fake_media(build_html(100))]
            queue.add(0, f)
            await queue.send_all()

        assert queue.sending is None
        bot = cast(FakeBot, queue.bot)
        assert not bot.log
        assert len(queue.exc_groups[f]) == grp_len
