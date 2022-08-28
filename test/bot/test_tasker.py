from time import time

import pytest
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html
from telegram import InputFile

from qzone3tg.bot.atom import (
    LIM_MD_TXT,
    LIM_TXT,
    LocalSplitter,
    MediaGroupPartial,
    PicPartial,
    TextPartial,
)
from qzone3tg.bot.limitbot import BotTaskEditter as BTE
from qzone3tg.bot.limitbot import BotTaskGenerator as BTG
from qzone3tg.bot.limitbot import RelaxSemaphore, TaskerEvent

from . import fake_feed, fake_media

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def gen():
    t = BTG(LocalSplitter())

    class FakeMarkup(TaskerEvent):
        async def reply_markup(self, feed):
            return 1, 1

    t.register_hook(FakeMarkup())
    yield t


@pytest.fixture(scope="class")
def edit(client: ClientAdapter):
    t = BTE(LocalSplitter(), client)
    t.register_hook(TaskerEvent())
    yield t


@pytest.mark.skip  # Semaphore is deprecated in 0.5.0a1
class TestSemaphore:
    async def test_acquire(self):
        sem = RelaxSemaphore(10)
        async with sem.context(10):
            assert not await sem.acquire(1, block=False)

    async def test_time(self):
        sem = RelaxSemaphore(10)
        async with sem.context(10):
            start = time()
        async with sem.context(1):
            assert time() - start > 1


class TestGenerator:
    async def test_msg_norm(self, gen: BTG):
        f = fake_feed(0)
        ps = [i async for i in gen.unify_send(f)]
        assert len(ps) == 1
        assert isinstance(ps[0], TextPartial)
        assert ps[0].reply_markup == 1

    async def test_msg_long(self, gen: BTG):
        f = fake_feed("a" * LIM_TXT)
        ps = [i async for i in gen.unify_send(f)]
        assert len(ps) == 2
        assert isinstance(ps[0], TextPartial)
        assert isinstance(ps[1], TextPartial)
        assert ps[0].reply_markup == 1
        assert ps[1].reply_markup is None

    async def test_media_norm(self, gen: BTG):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))]
        ps = [i async for i in gen.unify_send(f)]
        assert len(ps) == 1
        assert isinstance(ps[0], PicPartial)

    async def test_media_long(self, gen: BTG):
        f = fake_feed("a" * LIM_MD_TXT)
        f.media = [fake_media(build_html(100))]
        ps = [i async for i in gen.unify_send(f)]
        assert len(ps) == 2
        assert isinstance(ps[0], PicPartial)
        assert isinstance(ps[1], TextPartial)

    async def test_media_group(self, gen: BTG):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))] * 2
        ps = [i async for i in gen.unify_send(f)]
        assert len(ps) == 1
        assert isinstance(ps[0], MediaGroupPartial)
        assert ps[0].reply_markup is None

    async def test_media_group_exd(self, gen: BTG):
        f = fake_feed("a" * LIM_MD_TXT)
        f.media = [fake_media(build_html(100))] * 11
        ps = [i async for i in gen.unify_send(f)]
        assert len(ps) == 2
        assert isinstance(ps[0], MediaGroupPartial)
        assert isinstance(ps[1], PicPartial)
        assert ps[1].text
        assert ps[0].reply_markup is None
        assert ps[1].reply_markup == 1

    async def test_media_group_forward_exd(self, gen: BTG):
        ff = fake_feed("a" * LIM_MD_TXT)
        ff.media = [fake_media(build_html(100))] * 11
        f = fake_feed("b")
        f.forward = ff
        ps = [i async for i in gen.unify_send(f)]
        assert len(ps) == 3
        assert isinstance(ps[0], MediaGroupPartial)
        assert isinstance(ps[1], PicPartial)
        assert isinstance(ps[2], TextPartial)
        assert ps[1].text
        assert ps[0].reply_markup is None
        assert ps[1].reply_markup == 1
        assert ps[2].reply_markup == 1


class TestEditter:
    async def test_force_bytes_ipm(self, edit: BTE):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))] * 2
        ps = [i async for i in edit.unify_send(f)]
        p = ps[0]
        assert isinstance(p, MediaGroupPartial)
        ipm = await edit.force_bytes_inputmedia(p.medias[0])
        assert isinstance(ipm.media, InputFile)
        assert ipm.media.input_file_content

    async def test_force_bytes(self, edit: BTE):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))] * 11
        ps = [i async for i in edit.unify_send(f)]
        assert len(ps) == 2
        assert isinstance(ps[0], MediaGroupPartial)
        assert isinstance(ps[1], PicPartial)

        p = await edit.force_bytes(ps[0])
        for i in p.medias:
            assert isinstance(i.media, InputFile)
            assert i.media.input_file_content

        p = await edit.force_bytes(ps[1])
        assert isinstance(p.content, bytes)
