from typing import Callable, Iterable, Optional, TypeVar

T = TypeVar('T')


def find_if(iter: Iterable[T], pred: Callable[[T], bool]) -> Optional[T]:
    """As that in C++

    Args:
        iter (Iterable[T]): iterator
        pred (Callable[[T], bool]): callable. return the first i if pred(i) == True

    Returns:
        Optional[T]: the first i that pred(i) == True
    """
    for i in iter:
        if pred(i): return i
