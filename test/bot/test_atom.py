import pytest
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html
from telegram import InputMedia

import qzone3tg.bot.atom as atom
from qzone3tg.bot.splitter import FetchSplitter, LocalSplitter

from . import fake_feed, fake_media

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def local():
    return LocalSplitter()


@pytest.fixture(scope="class")
def fetch(client: ClientAdapter):
    return FetchSplitter(client)


async def test_media_arg():
    vm = fake_media(build_html(100))
    d = {
        atom.PicPartial: atom.Pic,
        atom.AnimPartial: atom.Anim,
        atom.DocPartial: atom.Doc,
        atom.VideoPartial: atom.Video,
    }
    for k, v in d.items():
        a = k(vm, None)
        assert isinstance(a.wrap_media(), v)


class TestLocal:
    async def test_msg_norm(self, local: LocalSplitter):
        f1 = fake_feed(1)
        pair = await local.split(f1, False)
        assert len(pair.forward) == 0
        assert len(pair.feed) == 1

        f1.forward = fake_feed(2)
        pair = await local.split(f1, True)
        assert len(pair.forward) == 1
        assert len(pair.feed) == 1

    async def test_msg_long(self, local: LocalSplitter):
        pair = await local.split(fake_feed("a" * atom.LIM_TXT), False)
        assert len(pair.feed) == 2

    async def test_media_norm(self, local: LocalSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))]
        pair = await local.split(f, False)
        assert len(pair.feed) == 1
        assert isinstance(pair.feed[0], atom.PicPartial)

        f.media[0] = fake_media(build_html(100, ext="gif"))
        pair = await local.split(f, False)
        assert len(pair.feed) == 1
        assert isinstance(pair.feed[0], atom.AnimPartial)

        f.media[0] = fake_media(build_html(100, ext="mp4"))
        f.media[0].is_video = True
        pair = await local.split(f, False)
        assert len(pair.feed) == 1
        assert isinstance(pair.feed[0], atom.VideoPartial)

    async def test_media_long(self, local: LocalSplitter):
        f = fake_feed("a" * atom.LIM_MD_TXT)
        f.media = [fake_media(build_html(100))]
        pair = await local.split(f, False)
        assert len(pair.feed) == 2
        assert isinstance(pair.feed[0], atom.PicPartial)
        assert isinstance(pair.feed[1], atom.TextPartial)

    async def test_media_group(self, local: LocalSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))] * 2
        pair = await local.split(f, False)
        assert len(pair.feed) == 1
        assert isinstance(pair.feed[0], atom.MediaGroupPartial)

        medias = pair.feed[0].medias
        assert all(isinstance(i, InputMedia) for i in medias)

    async def test_media_group_exd(self, local: LocalSplitter):
        f = fake_feed("a" * atom.LIM_MD_TXT)
        f.media = [fake_media(build_html(100))] * 11
        pair = await local.split(f, False)
        assert len(pair.feed) == 2
        assert isinstance(pair.feed[0], atom.MediaGroupPartial)
        assert isinstance(pair.feed[1], atom.PicPartial)
        assert pair.feed[0].text
        assert pair.feed[1].text

        medias = pair.feed[0].medias
        assert all(isinstance(i, InputMedia) for i in medias)


class TestFetch:
    async def test_media_norm(self, fetch: FetchSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))]
        pair = await fetch.split(f, False)
        assert len(pair.feed) == 1
        assert isinstance(pair.feed[0], atom.PicPartial)
        assert pair.feed[0]._raw

        f.media[0] = fake_media(build_html(100, ext="gif"))
        pair = await fetch.split(f, False)
        assert len(pair.feed) == 1
        assert isinstance(pair.feed[0], atom.AnimPartial)
        assert pair.feed[0]._raw

        f.media[0] = fake_media(build_html(100, ext="mp4"))
        f.media[0].is_video = True
        pair = await fetch.split(f, False)
        assert len(pair.feed) == 1
        assert isinstance(pair.feed[0], atom.VideoPartial)
