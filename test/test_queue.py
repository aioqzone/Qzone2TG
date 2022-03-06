import asyncio

from aioqzone_feed.type import FeedContent
import pytest

from qzone3tg.bot.queue import EditableQueue
from qzone3tg.bot.queue import StorageEvent
from qzone3tg.utils.iter import empty

pytestmark = pytest.mark.asyncio


class Feed4Test(FeedContent):
    def __hash__(self) -> int:
        return hash(self.content)


def fake_feed(i):
    o = Feed4Test.__new__(Feed4Test)
    object.__setattr__(o, "content", i)
    object.__setattr__(o, "forward", None)
    return o


async def test_seq_last():
    sched = EditableQueue()
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(10))
    for i in seq:
        await sched.add(i, fake_feed(i))
    sched.set_upper_bound(len(seq))

    assert len(hook.record) == 0
    await sched.send_all()
    seq.reverse()
    assert hook.record == seq


async def test_seq_first():
    sched = EditableQueue(10)
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(10))
    for i in seq:
        await sched.add(i, fake_feed(i))

    assert len(list(sched.pending_feeds())) == 9  # the last feed is submit
    assert len(hook.record) == 0  # but the task hasn't run
    await sched.send_all()
    seq.reverse()
    assert hook.record == seq


async def test_reverse_last():
    sched = EditableQueue()
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(9, -1, -1))
    for i in seq:
        await sched.add(i, fake_feed(i))
    sched.set_upper_bound(len(seq))

    assert len(hook.record) == 0
    await sched.send_all()
    assert hook.record == seq


async def test_reverse_first():
    sched = EditableQueue(10)
    sched.register_hook(hook := FwdEvt_Norm())
    seq = list(range(9, -1, -1))
    for i in seq:
        await sched.add(i, fake_feed(i))
        await asyncio.sleep(0)
        assert sched._waiting == i

    assert empty(iter(sched.pending_feeds()))
    await sched.send_all()
    assert hook.record == seq


async def test_err_all():
    sched = EditableQueue(5)
    sched.register_hook(hook := FwdEvt_Buggy())
    for i in range(5):
        await sched.add(i, fake_feed(i))
    await sched.send_all()
    assert all(len(l) == 2 for l in sched.excs.values())
    assert len(hook.err) == 5
    assert all(i == 2 for i in hook.err.values())


async def test_err_erpt():
    sched = EditableQueue(5)
    sched.register_hook(hook := FwdEvt_Buggy(3))
    for i in range(5):
        await sched.add(i, fake_feed(i))
    await sched.send_all()
    # assert len(sched.excs[3]) == 2
    assert len(hook.err) == len(hook.on)
    assert hook.err[3] == sched.retry
    assert hook.record == [4, 3, 3, 2, 1, 0]


async def test_forward():
    sched = EditableQueue(10)
    sched.register_hook(hook := FwdEvt_Norm())
    hook.register_hook(StorageEvent())
    for i in range(5):
        m = fake_feed(i << 1)
        object.__setattr__(m, "forward", fake_feed(i * 2 + 1))
        await sched.add(i, m)
    await sched.send_all()
    assert hook.record == sorted(range(10), reverse=True)


async def test_err_forward():
    sched = EditableQueue(5)
    sched.register_hook(hook := FwdEvt_Buggy(3, 5, 8))
    hook.register_hook(StorageEvent())
    for i in range(5):
        m = fake_feed(i << 1)
        object.__setattr__(m, "forward", fake_feed(i * 2 + 1))
        await sched.add(i, m)
    await sched.send_all()
    assert len(hook.err) == len(hook.on)
    assert hook.record == [9, 8, 8, 7, 6, 5, 5, 4, 3, 3, 2, 1, 0]
