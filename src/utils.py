import base64
from typing import Callable, Iterable, Optional, TypeVar
from demjson import undefined

T = TypeVar('T')


def pwdTransform(pwd: str, prefex='$'):
    return prefex + base64.b64encode(pwd.encode('utf8')).decode('utf8')


def pwdTransBack(pwd: str, prefex='$'):
    if pwd.startswith(prefex):
        return base64.b64decode(pwd.encode('utf8')).decode('utf8')
    else:
        return pwd


def undefined2None(dic: dict):
    for k, v in {dict: lambda d: dict.items(d), list: enumerate}[type(dic)](dic):
        if v is undefined: dic[k] = None
        elif isinstance(v, (dict, list)): undefined2None(v)
    return dic


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
