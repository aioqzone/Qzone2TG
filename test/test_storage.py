import asyncio
from random import randint
from time import time

import pytest
import pytest_asyncio
from aioqzone_feed.type import BaseFeed

from qzone3tg.app.storage import AsyncEnginew, DefaultStorageHook, FeedOrm
from qzone3tg.app.storage.orm import MessageOrm

pytestmark = pytest.mark.asyncio


def randhex(B: int = 4):
    p = (hex(randint(0, 0xFFFFFFFF))[2:] for _ in range(B))
    return "".join(p)


def randint_(a: float, b: float):
    return randint(int(a), int(b))


def fake_feed():
    return BaseFeed(
        appid=randint(200, 400),
        typeid=randint(0, 10000),
        fid=randhex(randint(4, 5)),
        abstime=randint_(time() - 86400, time()),
        uin=randint_(1e8, 1e9),
        nickname=str(randint(0, 100)),
    )


@pytest.fixture(scope="module")
def fixed():
    l = [fake_feed(), fake_feed(), fake_feed()]
    return l


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def store():
    async with AsyncEnginew.sqlite3(None) as engine:
        yield DefaultStorageHook(engine)


async def test_create(store: DefaultStorageHook):
    await store.create()


async def test_insert(store: DefaultStorageHook, fixed: list):
    await store.SaveFeed(fixed[1])
    await store.SaveFeed(fixed[2], [0])


async def test_exist(store: DefaultStorageHook, fixed: list):
    assert not await store.Exists(fixed[0])
    assert not await store.Exists(fixed[1])
    assert await store.Exists(fixed[2])


async def test_update(store: DefaultStorageHook, fixed: list):
    pack = await store.get(*FeedOrm.primkey(fixed[1]))
    assert pack
    feed, mids = pack
    assert mids is None

    await store.UpdateMid(fixed[2], [1, 2])
    mids = await store.GetMid(fixed[2])
    assert mids
    assert mids == [1, 2]


async def test_mid2feed(store: DefaultStorageHook, fixed: list):
    feed = await store.Mid2Feed(1)
    assert feed == fixed[2]


async def test_remove(store: DefaultStorageHook, fixed: list):
    await store.Clean(0)  # clean all
    assert not await store.Exists(fixed[2])
    assert await store.get_msg_orms(MessageOrm.mid == 1) is None
