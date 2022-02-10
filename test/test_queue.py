import asyncio

from aioqzone_feed.type import FeedContent
import pytest

from qzone3tg.bot.queue import ForwardEvent
from qzone3tg.bot.queue import MsgScheduler

pytestmark = pytest.mark.asyncio


class Feed4Test(FeedContent):
    def __hash__(self) -> int:
        return hash(self.content)


def fake_feed(i):
    o = Feed4Test.__new__(Feed4Test)
    object.__setattr__(o, 'content', i)
    return o


class FwdEvt_Norm(ForwardEvent):
    def __init__(self) -> None:
        self.record = []

    async def SendNow(self, feed: FeedContent):
        self.record.append(feed.content)

    async def FeedDroped(self, feed: FeedContent, *exc):
        assert False


class FwdEvt_Buggy(ForwardEvent):
    def __init__(self, *on: int) -> None:
        self.record = []
        self.err = {}
        self.on = on

    async def SendNow(self, feed: FeedContent):
        if not self.on or feed.content in self.on: raise NotImplementedError
        self.record.append(feed.content)

    async def FeedDroped(self, feed: FeedContent, *exc):
        self.err[feed.content] = len(exc)


async def test_seq_last():
    sched = MsgScheduler()
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(10))
    for i in seq:
        sched.add(i, fake_feed(i))
    sched.set_upper_bound(len(seq))

    assert len(hook.record) == 0
    await sched.send_all()
    seq.reverse()
    assert hook.record == seq


async def test_seq_first():
    sched = MsgScheduler(10)
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(10))
    for i in seq:
        sched.add(i, fake_feed(i))

    assert all(i is None for i in sched.buffer.values())
    assert len(hook.record) == 0
    await sched.send_all()
    seq.reverse()
    assert hook.record == seq


async def test_reverse_last():
    sched = MsgScheduler()
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(9, -1, -1))
    for i in seq:
        sched.add(i, fake_feed(i))
    sched.set_upper_bound(len(seq))

    assert len(hook.record) == 0
    await sched.send_all()
    assert hook.record == seq


async def test_reverse_first():
    sched = MsgScheduler(10)
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(9, -1, -1))
    for i in seq:
        sched.add(i, fake_feed(i))

    assert all(i is None for i in sched.buffer.values())
    await sched.send_all()
    assert hook.record == seq
    assert all(i is None for i in sched.buffer.values())


async def test_random_first():
    sched = MsgScheduler(10)
    sched.register_hook(hook := FwdEvt_Norm())
    for i in [8, 7]:
        sched.add(i, fake_feed(i))
    assert all(isinstance(i, FeedContent) for i in sched.buffer.values())
    sched.add(9, fake_feed(9))
    assert all(i is None for i in sched.buffer.values())

    for i in range(6):
        sched.add(i, fake_feed(i))
    assert all(isinstance(sched.buffer[i], FeedContent) for i in range(6))
    sched.add(6, fake_feed(6))
    assert all(i is None for i in sched.buffer.values())

    await sched.send_all()
    assert hook.record == sorted(range(10), reverse=True)
    assert all(i is None for i in sched.buffer.values())


async def test_random_mid():
    sched = MsgScheduler()
    sched.register_hook(hook := FwdEvt_Norm())
    for i in [9, 8, 7]:
        sched.add(i, fake_feed(i))
    assert all(isinstance(i, FeedContent) for i in sched.buffer.values())
    sched.set_upper_bound(10)
    sched.add(6, fake_feed(6))
    assert all(i is None for i in sched.buffer.values())

    for i in range(5):
        sched.add(i, fake_feed(i))
    assert all(isinstance(sched.buffer[i], FeedContent) for i in range(5))
    sched.add(5, fake_feed(5))
    assert all(i is None for i in sched.buffer.values())

    await sched.send_all()
    assert hook.record == sorted(range(10), reverse=True)
    assert all(i is None for i in sched.buffer.values())


async def test_err_all():
    sched = MsgScheduler(5)
    sched.register_hook(hook := FwdEvt_Buggy())
    for i in range(5):
        sched.add(i, fake_feed(i))
    await sched.send_all()
    assert all(len(l) == 2 for l in sched.excs.values())
    assert len(hook.err) == 5
    assert all(i == 2 for i in hook.err.values())


async def test_err_erpt():
    sched = MsgScheduler(5)
    sched.register_hook(hook := FwdEvt_Buggy(3))
    for i in range(5):
        sched.add(i, fake_feed(i))
    await sched.send_all()
    # assert len(sched.excs[3]) == 2
    assert len(hook.err) == 1
    assert hook.err[3] == 2
    assert hook.record == [4, 2, 1, 0]
