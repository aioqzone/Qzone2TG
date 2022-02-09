import asyncio
from random import randint
from time import time

from aioqzone_feed.type import BaseFeed
import pytest
import pytest_asyncio

from qzone2tg.app.interact import InteractStorageHook
from qzone2tg.app.storage import AsyncEnginew
from qzone2tg.app.storage import FeedOrm

pytestmark = pytest.mark.asyncio


def randhex(B: int = 4):
    p = (hex(randint(0, 0xffffffff))[2:] for _ in range(B))
    return ''.join(p)


def randint_(a: float, b: float):
    return randint(int(a), int(b))


def fake_feed():
    return BaseFeed(
        appid=randint(200, 400),
        typeid=randint(0, 10000),
        fid=randhex(randint(4, 5)),
        abstime=randint_(time() - 86400, time()),
        uin=randint_(1E8, 1E9),
        nickname=str(randint(0, 100))
    )

@pytest.fixture(scope='module')
def fixed():
    l = [fake_feed(), fake_feed()]
    return l


@pytest.fixture(scope='module')
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope='module')
async def store():
    async with AsyncEnginew.sqlite3(None) as engine:
        yield InteractStorageHook(engine)


async def test_create(store: InteractStorageHook):
    await store.create()


async def test_insert(store: InteractStorageHook, fixed: list):
    await store.SaveFeed(fixed[0])


async def test_exist(store: InteractStorageHook, fixed: list):
    assert not await store.exists(fixed[1])
    assert await store.exists(fixed[0])


async def test_update(store: InteractStorageHook, fixed: list):
    feed = await store.get_orm(FeedOrm.fid == fixed[0].fid)
    assert feed.mids is None    # type: ignore

    await store.update_message_id(fixed[0], [0])
    _, mids = await store.get(FeedOrm.fid == fixed[0].fid)    # type: ignore
    assert mids == [0]


async def test_remove(store: InteractStorageHook, fixed: list):
    await store.clean(0)    # clean all
    assert not await store.exists(fixed[0])
