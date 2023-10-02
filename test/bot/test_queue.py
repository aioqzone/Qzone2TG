from collections import defaultdict
from typing import cast
from unittest.mock import patch

import pytest
from aiogram import Bot
from aiogram.error import BadRequest, TimedOut
from aioqzone.model import PersudoCurkey
from aioqzone_feed.type import FeedContent
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html

from qzone3tg.bot.queue import MsgQueue, is_atoms, is_mids
from qzone3tg.bot.splitter import FetchSplitter
from qzone3tg.type import FeedPair

from . import FakeBot, fake_feed, fake_media

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture
def queue(client: ClientAdapter, fake_bot: Bot):
    return MsgQueue(fake_bot, FetchSplitter(client), defaultdict(int))


class TestQueue:
    async def test_add(self, queue: MsgQueue):
        queue.new_batch(0)
        f = fake_feed(0)
        queue.add(0, f)
        assert len(queue.Q) == 1
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert queue.Q[f].feed and is_mids(queue.Q[f].feed)

        queue.add(1, f)
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert len(queue.Q) == 1

        f = fake_feed(1)
        f.uin = 1
        queue.add(0, f)
        assert len(queue.Q) == 2
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert queue.Q[f].feed and is_atoms(queue.Q[f].feed)

        f = fake_feed(2)
        f.uin = 2
        f.forward = fake_feed(0)
        queue.add(0, f)
        assert len(queue.Q) == 3
        await queue.wait(PersudoCurkey(f.uin, f.abstime))
        assert queue.Q[f].feed and is_atoms(queue.Q[f].feed)
        assert queue.Q[f].forward and is_mids(queue.Q[f].forward)

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

        assert sum((i.feed for i in queue.Q.values()), []) == [1, 1, 2, 1]

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
