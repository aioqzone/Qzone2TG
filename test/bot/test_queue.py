import asyncio
from collections import defaultdict
from typing import cast
from unittest.mock import patch

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html

from qzone3tg.bot.queue import SendQueue, all_is_atom, all_is_mid
from qzone3tg.bot.splitter import FetchSplitter

from . import FakeBot, fake_feed, fake_media

pytestmark = pytest.mark.asyncio
_bad_request = TelegramBadRequest("POST", "Wrong file identifier/http url specified")  # type: ignore


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture
def queue(client: ClientAdapter, fake_bot: Bot) -> SendQueue:
    q = SendQueue(fake_bot, FetchSplitter(client), defaultdict(int))

    async def _unified_markup(feed):
        return InlineKeyboardMarkup(inline_keyboard=[])

    q.reply_markup = _unified_markup
    return q


class TestQueue:
    async def test_add(self, queue: SendQueue):
        # test normal situation
        queue.new_batch(0)
        f = fake_feed(0)
        queue.add(0, f)
        await queue.ch_feed[f].wait()
        assert len(queue.feed_state) == 1
        assert queue.feed_state[f] and all_is_mid(queue.feed_state[f])

        # test batch mismatch
        queue.add(1, f)
        await queue.ch_feed[f].wait()
        assert len(queue.feed_state) == 1

        # test add another uin but the same abstime
        f = fake_feed(1)
        f.uin = 1
        queue.add(0, f)
        await queue.ch_feed[f].wait()
        assert len(queue.feed_state) == 2
        assert queue.feed_state[f] and all_is_atom(queue.feed_state[f])

        # reference the first feed
        f = fake_feed(2)
        f.abstime = 2000
        f.forward = fake_feed(0)
        queue.add(0, f)
        assert len(queue.feed_state) == 3
        await queue.ch_feed[f].wait()
        assert queue.feed_state[f] and all_is_atom(queue.feed_state[f])

    async def test_drop_dup_feed(self, queue: SendQueue):
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

        queue.send_all()
        await queue.wait_all()
        bot = cast(FakeBot, queue.bot)
        assert len(bot.log) == 2

    async def test_send_norm(self, queue: SendQueue):
        queue.new_batch(1)
        for i in range(3):
            f = fake_feed(i + 1)
            f.abstime = i * 1000
            queue.add(1, f)
        queue.send_all()
        await queue.wait_all()
        bot = cast(FakeBot, queue.bot)
        assert len(bot.log) == 3
        assert "".join(i[2][-1] for i in bot.log) == "123"

    async def test_reply_markup(self, queue: SendQueue):
        f = fake_feed(2)
        f.forward = fake_feed(1)
        queue.new_batch(2)
        queue.add(2, f)
        queue.send_all()
        await queue.wait_all()
        bot = cast(FakeBot, queue.bot)
        assert len(bot.log) == 2
        for i in bot.log:
            assert isinstance(i[-1]["reply_markup"], InlineKeyboardMarkup)

    @pytest.mark.parametrize(
        ["exc2r", "grp_len"],
        [
            (asyncio.TimeoutError, 2),
            (_bad_request, 2),
            (RuntimeError, 1),
        ],
    )
    async def test_send_retry(self, queue: SendQueue, exc2r: Exception, grp_len: int):
        queue.new_batch(0)
        with patch.object(FakeBot, "send_photo", side_effect=exc2r):
            f = fake_feed(1)
            f.media = [fake_media(build_html(100))]
            queue.add(0, f)
            queue.send_all()
            await queue.wait_all()

        bot = cast(FakeBot, queue.bot)
        assert not bot.log
        assert len(queue.exc_groups[f]) == grp_len
