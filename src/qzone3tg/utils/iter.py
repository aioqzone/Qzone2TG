from typing import AsyncGenerator, Callable, Iterable, Iterator, TypeVar

It = TypeVar("It", str, list, tuple)
T = TypeVar("T")


def split_by_len(it: It, lens: int) -> list[It]:
    """
    The split_by_len function splits an iterator into a list of iterators,
    each with number of elements leq `lens` .

    :param it: Used to Specify the iterator that is passed in.
    :param lens: Used to Specify the length of each sub-iterator.
    :return: A list of iterators.
    """

    return [it[i : i + lens] for i in range(0, len(it), lens)]


async def alist(it: AsyncGenerator[T, None]) -> list[T]:
    """
    The alist function converts an async generator to a list.

    :param it: the async generator.
    :return: A list of all the values in the async generator.
    """

    return [i async for i in it]


async def aenumerate(
    it: AsyncGenerator[T, None], start: int = 0
) -> AsyncGenerator[tuple[int, T], None]:
    i = start
    async for e in it:
        yield i, e
        i += 1


def empty(it: Iterable | Iterator) -> bool:
    """
    The empty function returns True if the iterator is empty, False otherwise.

    :param it:Iterator: An iterable or an iterator.
    :return: True if the iterator is empty.

    .. note: If it is an iterator, it will be stepped once.
    """
    try:
        next(it if isinstance(it, Iterator) else iter(it))
        return False
    except StopIteration:
        return True


def countif(it: Iterable[T], cond: Callable[[T], bool], initial: bool = False) -> int:
    """
    The countif function counts the number of items in an iterator that satisfy a predicate.
    The predicate is a function that takes one argument in the iterator and returns a boolean.
    If `initial` is True, then only the initial items in the iterator will be counted.

    :param it:: iterator.
    :param cond:: predicate.
    :param initial: Used to Indicate whether to stop counting as soon as the condition is not met.
    :return: The number of elements in the iterator that satisfy the given condition.
    """

    cnt = 0
    for i in it:
        if cond(i):
            cnt += 1
        elif initial:
            return cnt
    return cnt
