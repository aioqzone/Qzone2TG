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

from qzone3tg.bot.queue import MsgQueue, QueueEvent, is_atoms, is_mids
from qzone3tg.bot.splitter import FetchSplitter
from qzone3tg.type import FeedPair

from . import FakeBot, fake_feed, fake_media

pytestmark = pytest.mark.asyncio


class Ihave0(QueueEvent):
    async def GetMid(self, feed: FeedContent) -> list[int] | None:
        if feed.entities[0].con == "0":  # type: ignore
            return [0]

    async def reply_markup(self, feed, need_forward: bool):
        return FeedPair(2, 1 if need_forward else None)


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
        assert queue.q[f].feed and is_mids(queue.q[f].feed)

        queue.add(1, f)
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert len(queue.q) == 1

        f = fake_feed(1)
        f.uin = 1
        queue.add(0, f)
        assert len(queue.q) == 2
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert queue.q[f].feed and is_atoms(queue.q[f].feed)

        f = fake_feed(2)
        f.uin = 2
        f.forward = fake_feed(0)
        queue.add(0, f)
        assert len(queue.q) == 3
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert queue.q[f].feed and is_atoms(queue.q[f].feed)
        assert queue.q[f].forward and is_mids(queue.q[f].forward)

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

    @pytest.mark.parametrize(
        ["feed", "forward", "markups"],
        [
            (fake_feed(2), fake_feed(1), [1, 2]),
            (fake_feed(2), fake_feed(0), [2]),
        ],
    )
    async def test_reply_markup(self, queue: MsgQueue, feed, forward, markups: list[int]):
        queue.new_batch(2)
        feed.forward = forward
        queue.add(2, feed)
        await queue.send_all()
        assert queue.sending is None
        bot = cast(FakeBot, queue.bot)
        assert len(bot.log) == len(markups)
        for i, markup in zip(bot.log, markups):
            assert i[-1]["reply_markup"] == markup

    @pytest.mark.parametrize(
        ["exc2r", "grp_len"],
        [
            (TimedOut, 2),
            # (BadRequest("Reply message not found"), 2),
            (BadRequest("Wrong file identifier/http url specified"), 2),
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
