from random import randint
from time import time

from aioqzone_feed.type import BaseFeed


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
