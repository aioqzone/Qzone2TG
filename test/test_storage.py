from pathlib import Path
from unittest import mock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from aioqzone.api.loginman import MixedLoginMan
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncEngineFactory
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from qzone3tg.app.storage import DefaultStorageHook, FeedOrm, StorageMan
from qzone3tg.app.storage.loginman import LoginMan
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
    async with AsyncEngineFactory.sqlite3(db) as engine:
        yield engine
    db.unlink(missing_ok=True)


@pytest_asyncio.fixture(scope="class")
async def store(engine: AsyncEngine):
    s = StorageMan(engine)
    await s.create()
    yield s


@pytest_asyncio.fixture(scope="class")
async def hook(store: StorageMan):
    yield DefaultStorageHook(store)


class TestFeedStore:
    async def test_create(self, store: StorageMan):
        await store.create()

    async def test_insert(self, hook: DefaultStorageHook, fixed: list):
        await hook.SaveFeed(fixed[1])
        await hook.SaveFeed(fixed[2], [0])

    async def test_exist(self, hook: DefaultStorageHook, fixed: list):
        assert not await hook.Exists(fixed[0])
        assert not await hook.Exists(fixed[1])
        assert await hook.Exists(fixed[2])

    async def test_update(self, store: StorageMan, hook: DefaultStorageHook, fixed: list):
        pack = await store.get(*FeedOrm.primkey(fixed[1]))
        assert pack
        feed, mids = pack
        assert not mids

        await hook.update_message_ids(fixed[2], [1, 2])
        mids = await hook.GetMid(fixed[2])
        assert mids
        assert mids == [1, 2]

    async def test_mid2feed(self, hook: DefaultStorageHook, fixed: list):
        feed = await hook.Mid2Feed(1)
        assert feed == fixed[2]

    async def test_remove(self, store: StorageMan, hook: DefaultStorageHook, fixed: list):
        await hook.Clean(0)  # clean all
        assert not await hook.Exists(fixed[2])
        assert not await store.get_msg_orms(MessageOrm.mid == 1)


class TestCookieStore:
    async def test_loginman_miss(self, engine: AsyncEngine, client: ClientAdapter):
        cookie = dict(errno=12)
        async with engine.begin() as conn:
            await conn.run_sync(CookieOrm.metadata.create_all)

        with mock.patch.object(MixedLoginMan, "_new_cookie", return_value=cookie):
            man = LoginMan(client, engine, 123, "forbid", "pwd")  # type: ignore
            await man.new_cookie()

        async with AsyncSession(engine) as sess:
            stmt = sa.select(CookieOrm).where(CookieOrm.uin == 123)
            r = await sess.scalar(stmt)
        assert r is None

    async def test_loginman_hit(self, engine: AsyncEngine, client: ClientAdapter):
        cookie = dict(p_skey="thisispskey")
        async with engine.begin() as conn:
            await conn.run_sync(CookieOrm.metadata.create_all)

        async with AsyncSession(engine) as sess:
            sess.add(CookieOrm(uin=123, p_skey="expiredpskey"))
            await sess.commit()

        man = LoginMan(client, engine, 123, "forbid", "pwd")  # type: ignore
        await man.load_cached_cookie()
        assert man._cookie["p_skey"] == "expiredpskey"

        with mock.patch.object(MixedLoginMan, "_new_cookie", return_value=cookie):
            await man.new_cookie()

        async with AsyncSession(engine) as sess:
            stmt = sa.select(CookieOrm).where(CookieOrm.uin == 123)
            r = await sess.scalar(stmt)
        assert r
        assert r.p_skey == cookie["p_skey"]
