import pytest
from middleware.storage import FeedBase
from qzone.parser import QZFeedParser


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

    def test0_Create(self):
        pass

    def test1_Insert(self):
        # yapf: disable
        feed = {'abstime': '100000000', 'appiconid': '311', 'appid': '311', 'bitmap': '', 'bor': '', 'clscFold': 'icenter_list_extend', 'commentcnt': '', 'dataonly': '0', 'emoji': [], 'feedno': '3', 'feedstime': '昨天 00:00', 'flag': '0', 'foldFeed': '', 'foldFeedTitle': '', 'hideExtend': '', 'html': '<li class="f-single f-s-s"><div class="f-single-foot"><div class="f-op-detail f-detail  content-line"><p class="op-list"><a class="item qz_like_btn_v3  item-on" data-islike="0" data-likecnt="4" data-unikey="" data-curkey=""></a></p></div></div></li>', 'info_user_display': '', 'info_user_name': '', 'key': '397e51599d4ef560321f0000', 'lastFeedBor': '', 'likecnt': '', 'list_bor2': '', 'logimg': '', 'mergeData': [None], 'moreflag': '', 'namecardLink': '', 'nickname': 'QAQ', 'oprType': '0', 'opuin': '8888888', 'otherflag': '0_0_0_0_0_0_0', 'ouin': '', 'relycnt': '', 'remark': '', 'rightflag': '', 'sameuser': {}, 'scope': '0', 'showEbtn': '', 'smallstar': '', 'summary': '', 'summaryTemp': '', 'title': '', 'titleTemp': '', 'type': '', 'typeid': '0', 'uin': '8888888', 'uper_isfriend': [], 'uperlist': [], 'upernum': '', 'userHome': '', 'ver': '1', 'vip': 'vip_0', 'yybitmap': '0042000000000000'}
        #yapf: enable
        feed = QZFeedParser(feed)
        if feed.fid in self.s.feed:
            pytest.skip('feed already in database')
        self.s.dumpFeed(feed)

    def test2_Read(self):
        assert (len(self.s.getFeed('abstime < 100000000')) == 0)
        a = self.s.feed['397e51599d4ef560321f0000']
        assert a is not None
        assert (a['fid'] == '397e51599d4ef560321f0000')
        assert (a['abstime'] == 100000000)

    def test3_GetUnsent(self):
        a = self.s.getFeed('is_sent IS NULL OR is_sent=0', 'tg')
        assert a

    def test4_Clean(self):
        assert len(self.s.getFeed())
        self.s.cleanFeed()
        assert len(self.s.getFeed()) == 0
        self.s.cursor.execute('select * from tg')
        assert len(self.s.cursor.fetchall()) == 0
        a = self.s.archive['397e51599d4ef560321f0000']
        assert a is not None

    @classmethod
    def teardown_class(cls) -> None:
        cls.s.close()
