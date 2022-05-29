import asyncio
from collections import defaultdict
from typing import Any, cast

import pytest
import pytest_asyncio
from aiohttp import ClientSession
from aioqzone_feed.type import FeedContent
from telegram.error import BadRequest, TimedOut

from qzone3tg.bot.atom import FetchSplitter
from qzone3tg.bot.limitbot import BotTaskEditter, RelaxSemaphore, TaskerEvent
from qzone3tg.bot.queue import EditableQueue, QueueEvent

from . import FakeBot, fake_feed

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def sess():
    async with ClientSession() as sess:
        yield sess


class Ihave0(QueueEvent):
    async def get_message_id(self, feed) -> list[int] | None:
        assert isinstance(feed, FeedContent)
        if feed.entities[0].con == "0":  # type: ignore
            return [0]


@pytest.fixture(scope="class")
def ideal(sess):
    sem = RelaxSemaphore(30)
    bot: Any = FakeBot()
    tasker = BotTaskEditter(bot, FetchSplitter(sess), sess)
    q = EditableQueue(tasker, defaultdict(int), sem)
    q.register_hook(Ihave0())

    class FakeMarkup(TaskerEvent):
        async def reply_markup(self, feed):
            return 1, 1

    tasker.register_hook(FakeMarkup())
    return q


class TestIdeal:
    async def test_add(self, ideal: EditableQueue):
        ideal.new_batch(0)
        f = fake_feed(0)
        await ideal.add(0, f)
        assert isinstance(ideal.q[f], int)
        await ideal.add(1, f)
        assert len(ideal.q) == 1
        f = fake_feed(1)
        f.uin = 1
        await ideal.add(0, f)
        assert len(ideal.q) == 2
        assert isinstance(ideal.q[f], list)

    async def test_send_norm(self, ideal: EditableQueue):
        ideal.new_batch(1)
        for i in range(3):
            f = fake_feed(i + 1)
            f.abstime = i
            await ideal.add(1, f)
        await ideal.send_all()
        assert ideal.sending is None
        bot = cast(FakeBot, ideal.tasker.bot)
        assert len(bot.log) == 3
        assert "".join(i[2][-1] for i in bot.log) == "123"

    async def test_reply_markup(self, ideal: EditableQueue):
        ideal.new_batch(2)
        f = fake_feed(2)
        f.forward = fake_feed(1)
        await ideal.add(2, f)
        await ideal.send_all()
        assert ideal.sending is None
        bot = cast(FakeBot, ideal.tasker.bot)
        dfw = bot.log[0][-1]
        df = bot.log[1][-1]
        assert dfw["reply_markup"] == 1
        assert df["reply_markup"] == 1


class RealBot(FakeBot):
    def send_message(self, chat_id, text: str, **kw):
        if e := kw.pop("e", None):
            raise e
        return super().send_message(chat_id, text, **kw)

    def send_media_group(self, chat_id, media: list, **kw):
        if e := kw.pop("e", None):
            raise e
        return super().send_media_group(chat_id, media, **kw)

    def send_photo(self, chat_id, photo: str | bytes, caption: str, **kw):
        if e := kw.pop("e", None):
            raise e
        return super().send_photo(chat_id, photo, caption, **kw)


@pytest.fixture(scope="class")
def real(sess):
    sem = RelaxSemaphore(30)
    bot: Any = RealBot()
    tasker = BotTaskEditter(bot, FetchSplitter(sess), sess)
    q = EditableQueue(tasker, defaultdict(int), sem)
    q.register_hook(Ihave0())
    tasker.register_hook(TaskerEvent())
    return q


class TestReal:
    async def test_send_retry(self, real: EditableQueue):
        real.new_batch(0)
        for i, e in zip(range(3), [TimedOut, BadRequest(""), RuntimeError]):
            f = fake_feed(i + 1)
            f.abstime = i
            await real.add(0, f)
            for p in real.q[f]:  # type: ignore
                p.keywords["e"] = e
        await real.send_all()
        assert ideal.sending is None
        bot = cast(FakeBot, real.tasker.bot)
        assert not bot.log
        assert len(real.exc) == 3
        assert [len(i) for i in real.exc.values()] == [2, 2, 2]
