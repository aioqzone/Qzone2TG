from abc import ABCMeta, abstractmethod
import re, base64, zlib
import sys

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
        assert 0 <= appid < 4096
        assert 0 <= typeid < 16
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
        assert len(key) <= 24
        self.key = key

    def tobytes(self):
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
        assert len(b) == 17
        return MoodUrl(
            str(int.from_bytes(b[:5], byteorder=sys.byteorder, signed=False)),
            Key.frombytes(b[5:]).key
        )


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

    def __init__(self, appid: int, typeid: int, key: str, unikey: str, curkey: str):
        self.appid = appid
        self.typeid = typeid
        self.key = key
        self.unikey = unikey
        self.curkey = curkey

    @property
    def fid(self):
        return self.key

    def tobytes(self):
        p = re.compile(r"http://.*/(\d+)/mood/(\w+)")
        t = p.search(self.unikey).groups()
        assert len(t) == 2
        uni = MoodUrl(*t)
        t = p.search(self.curkey).groups()
        assert len(t) == 2
        cur = MoodUrl(*t)
        key = Key(self.key)
        ids = IDs(self.appid, self.typeid)
        return ids.tobytes() + key.tobytes() + uni.tobytes() + cur.tobytes()

    def tostr(self):
        "decoding in ascii(128 chars)"
        b = zlib.compress(self.tobytes(), 9)
        assert len(b) <= 48
        return base64.b64encode(b, b'!-').decode(encoding)

    @staticmethod
    def frombytes(b: bytes):
        assert len(b) == 48
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
        assert len(b) <= 48
        return LikeId.frombytes(zlib.decompress(b))
