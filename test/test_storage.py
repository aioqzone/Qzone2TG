import pytest
from qzone2tg.middleware.storage import FeedBase


class TestSql:
    @classmethod
    def setup_class(cls) -> None:
        cls.s = FeedBase(
            'data/test.db',
            plugins={'tg': {
                'is_sent': 'BOOLEAN default 0'
            }},
            keepdays=0,
            archivedays=0
        )

    def test_Create(self):
        pass

    def test_Insert(self):
        # yapf: disable
        feed = {'abstime': '100000000', 'appid': '311', 'html': '<li class="f-single f-s-s"><div class="f-single-foot"><div class="f-op-detail f-detail  content-line"><p class="op-list"><a class="item qz_like_btn_v3  item-on" data-islike="0" data-likecnt="4" data-unikey="" data-curkey=""></a></p></div><img src="/ac/b.gif" onload="QZFL.media.reduceImage(0,560,560,{trueSrc:\'http:\\/\\/a1.qpic.cn\\/psc?\\/V11cTdQAQGzZn6\\/ruAMsa53pVQWN7FLK88i5hAjdROKkLOVJBihC6WJ4kaFwQyL9bZ2QAQBGzlY7mjCxmGzEU3tEJXS.R*KnYcadUx.9j8pwh2V1mFHk4gk2xE!\\/c&amp;ek=1&amp;kp=1&amp;pt=0&amp;tl=1&amp;vuin=12345678&amp;tm=1629450000&amp;sce=60-2-2&amp;rf=0-0\',callback:function(img,type,ew,eh,o){var _h = Math.floor(o.oh/o.k),_w = Math.floor(o.ow/o.k);if(_w<=ew && _h<=eh){var p=img.parentNode;p.style.width=_w+\'px\';p.style.height=_h+\'px\';}}})" /></div></li>', 'fid': '397e51599d4ef560321f0000', 'nickname': 'QAQ', 'typeid': '0', 'uin': '8888888'}
        #yapf: enable
        if feed['fid'] in self.s.feed:
            pytest.skip('feed already in database')
        self.s.feed[feed['fid']] = feed

    def test_Read(self):
        assert (len(self.s.getFeed('abstime < 100000000')) == 0)
        a = self.s.feed['397e51599d4ef560321f0000']
        assert a is not None
        assert (a['fid'] == '397e51599d4ef560321f0000')
        assert (a['abstime'] == 100000000)

    def test_GetUnsent(self):
        a = self.s.getFeed('is_sent IS NULL OR is_sent=0', 'tg')
        assert a

    def test_Clean(self):
        assert len(self.s.getFeed())
        from qzone2tg.qzone.parser import QzJsonParser
        self.s.cleanFeed(lambda d: QzJsonParser(d).getLikeId())
        assert len(self.s.getFeed()) == 0
        self.s.cursor.execute('select * from tg')
        assert len(self.s.cursor.fetchall()) == 0
        a = self.s.archive['397e51599d4ef560321f0000']
        assert a is not None

    @classmethod
    def teardown_class(cls) -> None:
        cls.s.close()
