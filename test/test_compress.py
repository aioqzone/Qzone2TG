from frontend.tg.compress import LikeId as lid
import pytest


class TestCompress:
    def setup(self):
        self.l = lid(
            311, 5, "1d5bbd5344bd435e2dd90d00",
            "http://user.qzone.qq.com/888888888/mood/1be2410b1cf6435e9f220900",
            "http://user.qzone.qq.com/1111111111/mood/1d5bbd5344bd435e2dd90d00"
        )

    def testToStr(self):
        s = self.l.tostr()
        assert len(s) == 64

    def testfromStr(self):
        s = self.l.tostr()
        i = lid.fromstr(s)
        assert i.appid == 311
        assert i.typeid == 5
        assert i.key == "1d5bbd5344bd435e2dd90d00"
        assert i.unikey == "http://user.qzone.qq.com/888888888/mood/1be2410b1cf6435e9f220900"
        assert i.curkey == "http://user.qzone.qq.com/1111111111/mood/1d5bbd5344bd435e2dd90d00"
