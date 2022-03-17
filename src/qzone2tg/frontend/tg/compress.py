import base64
import re
import sys
import zlib
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass

encoding = 'utf-8'


class Compress(metaclass=ABCMeta):
    @abstractmethod
    def tobytes(self):
        raise NotImplementedError()

    @staticmethod
    def frombytes(b: bytes):
        raise NotImplementedError()


class IDs(Compress):
    appid: int
    typeid: int

    def __init__(self, appid, typeid):
        assert 0 <= appid < 4096, appid
        assert 0 <= typeid < 16, typeid
        self.appid = appid
        self.typeid = typeid

    def tobytes(self):
        t = (self.appid << 4) + self.typeid
        return t.to_bytes(2, sys.byteorder, signed=False)

    @staticmethod
    def frombytes(b):
        t = int.from_bytes(b, byteorder=sys.byteorder, signed=False)
        return IDs(t >> 4, t & 0xf)


class Key(Compress):
    key: str

    def __init__(self, key: str):
        self.key = key

    def tobytes(self):
        assert len(self.key) <= 24
        return int(self.key, base=16).to_bytes(12, sys.byteorder, signed=False)

    @staticmethod
    def frombytes(b: bytes):
        return Key(
            '{:x}'.format(int.from_bytes(b, byteorder=sys.byteorder, signed=False))
        )


class MoodUrl(Compress):
    uin: int
    key: str

    def __init__(self, uin: str, key: str):
        self.uin = int(uin)
        self.key = key

    def tobytes(self):
        return self.uin.to_bytes(
            5, sys.byteorder, signed=False
        ) + Key(self.key).tobytes()

    @staticmethod
    def frombytes(b: bytes):
        assert len(b) == 17, len(b)
        return MoodUrl(
            str(int.from_bytes(b[:5], byteorder=sys.byteorder, signed=False)),
            Key.frombytes(b[5:]).key
        )


@dataclass(eq=True)
class LikeId(Compress):
    '''
    compress do_like args to 52 bytes, 
    for telegram api requires a "callback_data" less than 64 bytes.

    support "appid = 311" now.
    '''
    appid: int
    typeid: int
    key: str
    unikey: str
    curkey: str

    def __post_init__(self):
        # TODO: py39
        self.unikey = self.unikey.replace(' ', '') #.removesuffix('/')
        self.curkey = self.curkey.replace(' ', '') #.removesuffix('/')

    @property
    def fid(self):
        return self.key

    def tobytes(self):
        p = re.compile(r"http://.*/(\d+)/mood/(\w+)")

        t = p.search(self.unikey)
        if t is None: return
        uni = MoodUrl(*t.groups())

        t = p.search(self.curkey)
        if t is None: return
        cur = MoodUrl(*t.groups())

        if any(len(i) > 24 for i in [uni.key, cur.key, self.key]): return

        key = Key(self.key)
        ids = IDs(self.appid, self.typeid)
        return ids.tobytes() + key.tobytes() + uni.tobytes() + cur.tobytes()

    def tostr(self):
        "decoding in ascii(128 chars)"
        b = self.tobytes()
        if b is None: return

        zb = zlib.compress(b, 9)               # b# = 48
        if len(zb) < len(b): b = zb            # zb# < 48
        assert len(b) <= 48, str(self.todict())

        return base64.b64encode(b, b'!-').decode(encoding)

    def todict(self):
        return {
            'unikey': self.unikey,
            'curkey': self.curkey,
            'appid': self.appid,
            'typeid': self.typeid,
            'key': self.key,
        }

    @staticmethod
    def frombytes(b: bytes):
        assert len(b) == 48, len(b)
        ids = IDs.frombytes(b[:2])
        uni = MoodUrl.frombytes(b[14:31])
        cur = MoodUrl.frombytes(b[31:48])
        url = "http://user.qzone.qq.com/{uin}/mood/{key}"
        return LikeId(
            ids.appid, ids.typeid,
            Key.frombytes(b[2:14]).key, url.format(uin=uni.uin, key=uni.key),
            url.format(uin=cur.uin, key=cur.key)
        )

    @staticmethod
    def fromstr(s: str):
        b = base64.b64decode(bytes(s, encoding=encoding), b'!-')
        assert len(b) <= 48, s
        if len(b) == 48: return LikeId.frombytes(b) # zb# < 48 |= zb#==48 => not zb
        return LikeId.frombytes(zlib.decompress(b))