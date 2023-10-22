import pytest
from aiogram.types import InputMedia
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html

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


class TestLocal:
    async def test_msg_norm(self, local: LocalSplitter):
        f1 = fake_feed(1)
        atoms = await local.split(f1)
        assert len(atoms) == 1

    async def test_msg_long(self, local: LocalSplitter):
        atoms = await local.split(fake_feed("a" * atom.LIM_TXT))
        assert len(atoms) == 2

    async def test_media_norm(self, local: LocalSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))]
        atoms = await local.split(f)
        assert len(atoms) == 1
        assert isinstance(atoms[0], atom.PicPartial)

        f.media[0] = fake_media(build_html(100, ext="gif"))
        atoms = await local.split(f)
        assert len(atoms) == 1
        assert isinstance(atoms[0], atom.AnimPartial)

        f.media[0] = fake_media(build_html(100, ext="mp4"))
        f.media[0].is_video = True
        atoms = await local.split(f)
        assert len(atoms) == 1
        assert isinstance(atoms[0], atom.VideoPartial)

    async def test_media_long(self, local: LocalSplitter):
        f = fake_feed("a" * atom.LIM_MD_TXT)
        f.media = [fake_media(build_html(100))]
        atoms = await local.split(f)
        assert len(atoms) == 2
        assert isinstance(atoms[0], atom.PicPartial)
        assert isinstance(atoms[1], atom.TextPartial)

    async def test_media_group(self, local: LocalSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))] * 2
        atoms = await local.split(f)
        assert len(atoms) == 1
        assert isinstance(gp := atoms[0], atom.MediaGroupPartial)

        medias = gp.builder._media
        assert all(isinstance(i, InputMedia) for i in medias)

    async def test_media_group_exd(self, local: LocalSplitter):
        f = fake_feed("a" * atom.LIM_MD_TXT)
        f.media = [fake_media(build_html(100))] * 11
        pair = await local.split(f)
        assert len(pair) == 2
        assert isinstance(gp := pair[0], atom.MediaGroupPartial)
        assert isinstance(pair[1], atom.PicPartial)
        assert pair[0].text
        assert pair[1].text

        medias = gp.builder._media
        assert all(isinstance(i, InputMedia) for i in medias)


class TestFetch:
    async def test_media_norm(self, fetch: FetchSplitter):
        f = fake_feed(1)
        f.media = [fake_media(build_html(100))]
        pair = await fetch.split(f)
        assert len(pair) == 1
        assert isinstance(pair[0], atom.PicPartial)
        assert pair[0]._raw

        f.media[0] = fake_media(build_html(100, ext="gif"))
        pair = await fetch.split(f)
        assert len(pair) == 1
        assert isinstance(pair[0], atom.AnimPartial)
        assert pair[0]._raw

        f.media[0] = fake_media(build_html(100, ext="mp4"))
        f.media[0].is_video = True
        pair = await fetch.split(f)
        assert len(pair) == 1
        assert isinstance(pair[0], atom.VideoPartial)
