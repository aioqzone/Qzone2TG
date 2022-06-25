import pytest
import pytest_asyncio
from qzemoji.base import AsyncEngineFactory

from qzone3tg.app.storage import DefaultStorageHook, FeedOrm, StorageMan
from qzone3tg.app.storage.orm import MessageOrm

from . import fake_feed

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def fixed():
    l = [fake_feed(), fake_feed(), fake_feed()]
    return l


@pytest_asyncio.fixture(scope="module")
async def store():
    async with AsyncEngineFactory.sqlite3(None) as engine:
        yield StorageMan(engine)


@pytest_asyncio.fixture(scope="module")
async def hook(store: StorageMan):
    yield DefaultStorageHook(store)


async def test_create(store: StorageMan):
    await store.create()


async def test_insert(hook: DefaultStorageHook, fixed: list):
    await hook.SaveFeed(fixed[1])
    await hook.SaveFeed(fixed[2], [0])


async def test_exist(hook: DefaultStorageHook, fixed: list):
    assert not await hook.Exists(fixed[0])
    assert not await hook.Exists(fixed[1])
    assert await hook.Exists(fixed[2])


async def test_update(store: StorageMan, hook: DefaultStorageHook, fixed: list):
    pack = await store.get(*FeedOrm.primkey(fixed[1]))
    assert pack
    feed, mids = pack
    assert mids is None

    await hook.UpdateMid(fixed[2], [1, 2])
    mids = await hook.GetMid(fixed[2])
    assert mids
    assert mids == [1, 2]


async def test_mid2feed(hook: DefaultStorageHook, fixed: list):
    feed = await hook.Mid2Feed(1)
    assert feed == fixed[2]


async def test_remove(store: StorageMan, hook: DefaultStorageHook, fixed: list):
    await hook.Clean(0)  # clean all
    assert not await hook.Exists(fixed[2])
    assert await store.get_msg_orms(MessageOrm.mid == 1) is None
