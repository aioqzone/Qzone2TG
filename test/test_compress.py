from qzone2tg.frontend.tg.compress import LikeId as lid
import pytest
from pathlib import Path


@pytest.fixture(scope='module')
def tlid():
    if (p := Path('tmp/json/compress.json')).exists():
        import json
        with open(p) as f:
            return lid(**json.load(f))

    return lid(
        311, 5, "1d5bbd5344bd435e2dd90d00",
        "http://user.qzone.qq.com/888888888/mood/1be2410b1cf6435e9f220900",
        "http://user.qzone.qq.com/1111111111/mood/1d5bbd5344bd435e2dd90d00"
    )


class TestCompress:
    def testToStr(self, tlid):
        s = tlid.tostr()
        assert len(s) == 64

    def testfromStr(self, tlid):
        s = tlid.tostr()
        i = lid.fromstr(s)
        assert i == tlid
