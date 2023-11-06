from pathlib import Path
from unittest import mock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from aioqzone.api import ConstLoginMan, Loginable
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncEngineFactory
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from qzone3tg.app.base import StorageMixin
from qzone3tg.app.storage import FeedOrm, StorageMan
from qzone3tg.app.storage.blockset import BlockSet
from qzone3tg.app.storage.loginman import *
from qzone3tg.app.storage.orm import CookieOrm, MessageOrm

from . import fake_feed

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def fixed():
    l = [fake_feed(), fake_feed(), fake_feed()]
    return l


@pytest_asyncio.fixture(scope="class")
async def engine():
    db = Path("tmp/tmp.db")
    db.unlink(missing_ok=True)
    async with AsyncEngineFactory.sqlite3(db) as engine:
        yield engine
    db.unlink(missing_ok=True)


@pytest_asyncio.fixture(scope="class")
async def store(engine: AsyncEngine):
    s = StorageMan(engine)
    await s.create()
    yield s


@pytest.fixture(scope="class")
def app(store: StorageMan):
    class fake_app(StorageMixin):
        def __init__(self, store) -> None:
            self.store = store

    return fake_app(store)


@pytest_asyncio.fixture(scope="class")
async def blockset(engine: AsyncEngine):
    s = BlockSet(engine)
    await s.create()
    yield s


class TestFeedStore:
    async def test_create(self, store: StorageMan):
        await store.create()

    async def test_insert(self, app: StorageMixin, fixed: list):
        await app.SaveFeed(fixed[1])
        await app.SaveFeed(fixed[2], [0])

    async def test_exist(self, store: StorageMan, fixed: list):
        assert not await store.exists(*FeedOrm.primkey(fixed[0]))
        assert not await store.exists(*FeedOrm.primkey(fixed[1]))
        assert await store.exists(*FeedOrm.primkey(fixed[2]))

    async def test_update(self, store: StorageMan, fixed: list):
        pack = await store.get(*FeedOrm.primkey(fixed[1]))
        assert pack
        feed, mids = pack
        assert not mids

    async def test_mid2feed(self, app: StorageMixin, fixed: list):
        await app._update_message_ids(fixed[2], [1, 2])
        feed = await app.Mid2Feed(1)
        assert feed == fixed[2]

    async def test_remove(self, store: StorageMan, fixed: list):
        await store.clean(0)  # clean all
        assert not await store.exists(*FeedOrm.primkey(fixed[2]))
        assert not await store.get_msg_orms(MessageOrm.mid == 1)


@pytest.fixture(scope="class")
def man() -> Loginable:
    return ConstLoginMan(123, {})


class TestCookieStore:
    async def test_loginman_miss(self, man: Loginable, engine: AsyncEngine):
        cookie = dict(errno="12")
        async with engine.begin() as conn:
            await conn.run_sync(CookieOrm.metadata.create_all)

        async with AsyncSession(engine) as sess:
            await save_cookie(cookie, 123, sess)
        with mock.patch.object(man, "_new_cookie", return_value=cookie):
            await man.new_cookie()

        async with AsyncSession(engine) as sess:
            stmt = sa.select(CookieOrm).where(CookieOrm.uin == 123)
            r = await sess.scalar(stmt)
        assert r is None

    async def test_loginman_hit(self, engine: AsyncEngine, man: Loginable):
        cookie = dict(p_skey="thisispskey", pt4_token="token")
        async with engine.begin() as conn:
            await conn.run_sync(CookieOrm.metadata.create_all)

        async with AsyncSession(engine) as sess:
            sess.add(CookieOrm(uin=123, p_skey="expiredpskey", pt4_token="expiredtoken"))
            await sess.commit()

        cookie = await load_cached_cookie(123, engine)
        assert cookie
        assert cookie["p_skey"] == "expiredpskey"
        assert cookie["pt4_token"] == "expiredtoken"

        with mock.patch.object(man, "_new_cookie", return_value=cookie):
            await man.new_cookie()

        async with AsyncSession(engine) as sess:
            stmt = sa.select(CookieOrm).where(CookieOrm.uin == 123)
            r = await sess.scalar(stmt)
        assert r
        assert r.p_skey == cookie["p_skey"]
        assert r.pt4_token == cookie["pt4_token"]


class TestBlockSet:
    async def test_add(self, blockset: BlockSet):
        await blockset.add(1)

    async def test_contains(self, blockset: BlockSet):
        assert await blockset.contains(1)

    async def test_delete(self, blockset: BlockSet):
        await blockset.delete(1)
        assert not await blockset.contains(1)

    async def test_list(self, blockset: BlockSet):
        async with blockset.sess() as sess:
            await blockset.add(1, sess=sess, flush=False)
            await blockset.add(2, sess=sess, flush=False)
            await blockset.add(3, sess=sess, flush=True)

        assert [1, 2, 3] == sorted(await blockset.all())
