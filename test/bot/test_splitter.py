from typing import Callable

import pytest
from aiogram import InputFile
from aiogram.constants import MediaGroupLimit
from qqqr.utils.net import ClientAdapter
from qzemoji.utils import build_html

from qzone3tg.bot.atom import (
    LIM_MD_TXT,
    LIM_TXT,
    DocPartial,
    MediaGroupPartial,
    MediaPartial,
    PicPartial,
    TextPartial,
)
from qzone3tg.bot.splitter import FetchSplitter, LocalSplitter

from . import fake_feed, fake_media, invalid_media

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def local():
    return LocalSplitter()


@pytest.fixture(scope="class")
def fetch(client: ClientAdapter):
    return FetchSplitter(client)


class TestLocal:
    async def test_msg_norm(self, local: LocalSplitter):
        f = fake_feed(0)
        ps = await local.unify_send(f)
        assert len(ps) == 1
        assert isinstance(ps[0], TextPartial)

    async def test_msg_long(self, local: LocalSplitter):
        f = fake_feed("a" * LIM_TXT)
        ps = await local.unify_send(f)
        assert len(ps) == 2
        assert isinstance(ps[0], TextPartial)
        assert isinstance(ps[1], TextPartial)

    async def test_media_norm(self, local: LocalSplitter):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))]
        ps = await local.unify_send(f)
        assert len(ps) == 1
        assert isinstance(ps[0], PicPartial)

    async def test_media_long(self, local: LocalSplitter):
        f = fake_feed("a" * LIM_MD_TXT)
        f.media = [fake_media(build_html(100))]
        ps = await local.unify_send(f)
        assert len(ps) == 2
        assert isinstance(ps[0], PicPartial)
        assert isinstance(ps[1], TextPartial)

    async def test_media_group(self, local: LocalSplitter):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))] * 2
        ps = await local.unify_send(f)
        assert len(ps) == 1
        assert isinstance(ps[0], MediaGroupPartial)
        assert ps[0].reply_markup is None

    async def test_media_group_exd(self, local: LocalSplitter):
        f = fake_feed("a" * LIM_MD_TXT)
        f.media = [fake_media(build_html(100))] * 11
        ps = await local.unify_send(f)
        assert len(ps) == 2
        assert isinstance(ps[0], MediaGroupPartial)
        assert isinstance(ps[1], PicPartial)
        assert ps[1].text

    async def test_media_group_forward_exd(self, local: LocalSplitter):
        ff = fake_feed("a" * LIM_MD_TXT)
        ff.media = [fake_media(build_html(100))] * 11
        f = fake_feed("b")
        f.forward = ff
        ps = await local.unify_send(f)
        assert len(ps) == 3
        assert isinstance(ps[0], MediaGroupPartial)
        assert isinstance(ps[1], PicPartial)
        assert isinstance(ps[2], TextPartial)
        assert ps[1].text

    async def test_media_group_doc(self, local: LocalSplitter):
        f = fake_feed("a")
        f.media = [invalid_media(build_html(100))] * 3
        ps = await local.unify_send(f)
        assert len(ps) == 1
        assert isinstance(ps[0], MediaGroupPartial)
        assert ps[0].is_doc

    @pytest.mark.parametrize(
        ["md_factory", "part_cls"],
        [
            ([invalid_media, fake_media, invalid_media], [DocPartial, PicPartial, DocPartial]),
            ([fake_media, fake_media, invalid_media], [MediaGroupPartial]),
            ([invalid_media, invalid_media, fake_media], [MediaGroupPartial, PicPartial]),
        ],
    )
    async def test_media_group_doc_exd(
        self, local: LocalSplitter, md_factory: list[Callable], part_cls: list[type[MediaPartial]]
    ):
        f = fake_feed("a")
        f.media = [f(build_html(i)) for i, f in enumerate(md_factory, 100)]
        ps = await local.unify_send(f)
        assert len(ps) == len(part_cls)
        for p, p_cls in zip(ps, part_cls):
            assert isinstance(p, p_cls)
            if isinstance(p, MediaGroupPartial):
                assert len(p.builder) >= MediaGroupLimit.MIN_MEDIA_LENGTH


class TestFetch:
    async def test_force_bytes_ipm(self, fetch: FetchSplitter):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))] * 2
        ps = await fetch.unify_send(f)
        p = ps[0]
        assert isinstance(p, MediaGroupPartial)
        ipm = await fetch.force_bytes_inputmedia(p.builder[0])
        assert isinstance(ipm.media, InputFile)
        assert ipm.media.input_file_content

    async def test_force_bytes(self, fetch: FetchSplitter):
        f = fake_feed(0)
        f.media = [fake_media(build_html(100))] * 11
        ps = await fetch.unify_send(f)
        assert len(ps) == 2
        assert isinstance(ps[0], MediaGroupPartial)
        assert isinstance(ps[1], PicPartial)

        p = await fetch.force_bytes(ps[0])
        for i in p.builder:
            assert isinstance(i.media, InputFile)
            assert i.media.input_file_content

        p = await fetch.force_bytes(ps[1])
        assert isinstance(p.content, bytes)
