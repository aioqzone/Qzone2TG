import pytest
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html
from telegram import InputMedia

import qzone3tg.bot.atom as atom

from . import fake_feed, fake_media

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def local():
    return atom.LocalSplitter()


@pytest.fixture(scope="class")
def fetch(client: ClientAdapter):
    return atom.FetchSplitter(client)


def test_media_arg():
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
    async def test_msg_norm(self, local: atom.LocalSplitter):
        f1 = fake_feed(1)
        w, a = await local.split(f1)
        assert len(w) == 0
        assert len(a) == 1

        f1.forward = fake_feed(2)
        w, a = await local.split(f1)
        assert len(w) == 1
        assert len(a) == 1

    async def test_msg_long(self, local: atom.LocalSplitter):
        _, f = await local.split(fake_feed("a" * atom.LIM_TXT))
        assert len(f) == 2

    async def test_media_norm(self, local: atom.LocalSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))]
        _, a = await local.split(f)
        assert len(a) == 1
        assert isinstance(a[0], atom.PicPartial)

        f.media[0] = fake_media(build_html(100, ext="gif"))
        _, a = await local.split(f)
        assert len(a) == 1
        assert isinstance(a[0], atom.AnimPartial)

        f.media[0] = fake_media(build_html(100, ext="mp4"))
        f.media[0].is_video = True
        _, a = await local.split(f)
        assert len(a) == 1
        assert isinstance(a[0], atom.VideoPartial)

    async def test_media_long(self, local: atom.LocalSplitter):
        f = fake_feed("a" * atom.LIM_MD_TXT)
        f.media = [fake_media(build_html(100))]
        _, a = await local.split(f)
        assert len(a) == 2
        assert isinstance(a[0], atom.PicPartial)
        assert isinstance(a[1], atom.TextPartial)

    async def test_media_group(self, local: atom.LocalSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))] * 2
        _, a = await local.split(f)
        assert len(a) == 1
        assert isinstance(a[0], atom.MediaGroupPartial)

        medias = a[0].medias
        assert all(isinstance(i, InputMedia) for i in medias)

    async def test_media_group_exd(self, local: atom.LocalSplitter):
        f = fake_feed("a" * atom.LIM_MD_TXT)
        f.media = [fake_media(build_html(100))] * 11
        _, a = await local.split(f)
        assert len(a) == 2
        assert isinstance(a[0], atom.MediaGroupPartial)
        assert isinstance(a[1], atom.PicPartial)
        assert a[0].text
        assert a[1].text

        medias = a[0].medias
        assert all(isinstance(i, InputMedia) for i in medias)


class TestFetch:
    async def test_media_norm(self, fetch: atom.FetchSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))]
        _, a = await fetch.split(f)
        assert len(a) == 1
        assert isinstance(a[0], atom.PicPartial)
        assert a[0]._raw

        f.media[0] = fake_media(build_html(100, ext="gif"))
        _, a = await fetch.split(f)
        assert len(a) == 1
        assert isinstance(a[0], atom.AnimPartial)
        assert a[0]._raw

        f.media[0] = fake_media(build_html(100, ext="mp4"))
        f.media[0].is_video = True
        _, a = await fetch.split(f)
        assert len(a) == 1
        assert isinstance(a[0], atom.VideoPartial)
