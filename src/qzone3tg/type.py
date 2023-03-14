from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

_T = TypeVar("_T")


@dataclass
class FeedPair(Generic[_T]):
    """This struct is useful to represent a pair of data associated with a feed
    and its :obj:`~FeedContent.forward` field.

    For example, for a feed that has a forward feed, this struct can be used to
    store the :mod:`atom`s of the two feeds seperately.
    """

    feed: _T
    forward: _T
