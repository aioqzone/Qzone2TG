import asyncio
from random import randint
from time import time

from aioqzone_feed.type import BaseFeed
import pytest
import pytest_asyncio

from qzone2tg.app.storage import FeedOrm
from qzone2tg.app.storage import FeedStore

pytestmark = pytest.mark.asyncio


def randhex(B: int = 4):
    p = (hex(randint(0, 0xffffffff))[2:] for _ in range(B))
    return ''.join(p)


def randint_(a: float, b: float):
    return randint(int(a), int(b))


def fake_feed(fid: str = None):
    return BaseFeed(
        appid=randint(200, 400),
        typeid=randint(0, 10000),
        fid=fid or randhex(randint(4, 5)),
        abstime=randint_(time() - 86400, time()),
        uin=randint_(1E8, 1E9),
        nickname=str(randint(0, 100))
    )


@pytest.fixture(scope='module')
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope='module')
async def store():
    async with FeedStore() as s:
        yield s


async def test_create(store: FeedStore):
    await store.create()


async def test_insert(store: FeedStore):
    feed = fake_feed('aabaaaba' * 4)
    await store.save(feed)


async def test_exist(store: FeedStore):
    assert not await store.exists('aabaaaba')
    assert await store.exists('aabaaaba' * 4)


async def test_update(store: FeedStore):
    from aioqzone.type import LikeData
    pred = FeedOrm.fid == 'aabaaaba' * 4
    feed = await store.get_orm(pred)
    assert feed

    curkey = LikeData.persudo_curkey(feed.uin, feed.abstime)    # type: ignore
    await store.edit(lambda o: setattr(o, 'curkey', curkey), pred)
    obj, _ = await store.get(pred)    # type: ignore
    assert obj.curkey == curkey


async def test_remove(store: FeedStore):
    await store.clean(0)    # clean all
    assert not await store.exists('aabaaaba' * 4)
