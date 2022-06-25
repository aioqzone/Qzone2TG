from collections import defaultdict
from typing import cast

import pytest
from aioqzone_feed.type import FeedContent
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html
from telegram.error import BadRequest, TimedOut

from qzone3tg.bot.atom import FetchSplitter
from qzone3tg.bot.limitbot import BotTaskEditter, RelaxSemaphore, TaskerEvent
from qzone3tg.bot.queue import EditableQueue, QueueEvent

from . import FakeBot, fake_feed, fake_media

pytestmark = pytest.mark.asyncio


class Ihave0(QueueEvent):
    async def GetMid(self, feed: FeedContent) -> list[int] | None:
        if feed.entities[0].con == "0":  # type: ignore
            return [0]


@pytest.fixture(scope="class")
def ideal(client: ClientAdapter):
    sem = RelaxSemaphore(30)
    bot = FakeBot()
    tasker = BotTaskEditter(FetchSplitter(client), client)
    q = EditableQueue(bot, tasker, defaultdict(int), sem)
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
        bot = cast(FakeBot, ideal.bot)
        assert len(bot.log) == 3
        assert "".join(i[2][-1] for i in bot.log) == "123"

    async def test_reply_markup(self, ideal: EditableQueue):
        ideal.new_batch(2)
        f = fake_feed(2)
        f.forward = fake_feed(1)
        await ideal.add(2, f)
        await ideal.send_all()
        assert ideal.sending is None
        bot = cast(FakeBot, ideal.bot)
        dfw = bot.log[0][-1]
        df = bot.log[1][-1]
        assert dfw["reply_markup"] == 1
        assert df["reply_markup"] == 1


class RealBot(FakeBot):
    def send_message(self, to, text: str, **kw):
        if e := kw.pop("e", None):
            raise e
        return super().send_message(to, text, **kw)

    def send_media_group(self, to, media: list, **kw):
        if e := kw.pop("e", None):
            raise e
        return super().send_media_group(to, media, **kw)

    def send_photo(self, to, media: str | bytes, text: str, **kw):
        if e := kw.pop("e", None):
            raise e
        return super().send_photo(to, media, text, **kw)


@pytest.fixture(scope="class")
def real(client: ClientAdapter):
    sem = RelaxSemaphore(30)
    bot = RealBot()
    tasker = BotTaskEditter(FetchSplitter(client), client)
    q = EditableQueue(bot, tasker, defaultdict(int), sem)
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

            l = real.q[f]
            assert isinstance(l, list)
            for p in l:
                p.kwds["e"] = e
        await real.send_all()
        assert real.sending is None
        bot = cast(RealBot, real.bot)
        assert not bot.log
        assert len(real.exc) == 3
        assert [len(i) for i in real.exc.values()] == [2, 1, 2]

    async def test_badrequest_media(self, real: EditableQueue):
        real.new_batch(1)
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))]
        await real.add(1, f)
        l = real.q[f]
        assert isinstance(l, list)
        for p in l:
            p.kwds["e"] = BadRequest("")
        await real.send_all()
        assert real.sending is None
        bot = cast(RealBot, real.bot)
        assert not bot.log
        assert len(real.exc) == 1
        assert len(real.exc[f]) == 2
