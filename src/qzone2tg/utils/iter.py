from typing import AsyncGenerator, Iterator, TypeVar

It = TypeVar('It', str, list, tuple)
T = TypeVar('T')


def split_by_len(it: It, lens: int) -> list[It]:
    return [it[i:i + lens] for i in range(0, len(it), lens)]


async def anext(it: AsyncGenerator[T, None], default=None) -> T:
    async for i in it:
        return i
    return default


async def anext_(it: AsyncGenerator[T, None]) -> T:
    async for i in it:
        return i
    raise StopAsyncIteration


async def alist(it: AsyncGenerator[T, None]) -> list[T]:
    return [i async for i in it]


def empty(it: Iterator) -> bool:
    return next(it, None) is None
