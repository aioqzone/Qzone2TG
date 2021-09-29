from typing import Callable, Iterable, TypeVar

T = TypeVar('T')


def find_if(it: Iterable[T], pred: Callable[[T], bool]):
    """As that in C++

    Args:
        iter (Iterable[T]): iterator
        pred (Callable[[T], bool]): callable. return the first i if pred(i) == True

    Returns:
        Optional[T]: the first i that pred(i) == True
    """
    return next(filter(pred, it), None)
