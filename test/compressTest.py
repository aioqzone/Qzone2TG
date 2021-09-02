from frontend.tg.compress import LikeId as lid
import unittest


class CompressTest(unittest.TestCase):
    def setUp(self):
        self.l = lid(
            311, 5, "1d5bbd5344bd435e2dd90d00",
            "http://user.qzone.qq.com/888888888/mood/1be2410b1cf6435e9f220900",
            "http://user.qzone.qq.com/1111111111/mood/1d5bbd5344bd435e2dd90d00"
        )

    def testToStr(self):
        s = self.l.tostr()
        self.assertLessEqual(len(s), 64)

    def testfromStr(self):
        s = self.l.tostr()
        i = lid.fromstr(s)
        self.assertEqual(i.appid, 311)
        self.assertEqual(i.typeid, 5)
        self.assertEqual(i.key, "1d5bbd5344bd435e2dd90d00")
        self.assertEqual(
            i.unikey, "http://user.qzone.qq.com/888888888/mood/1be2410b1cf6435e9f220900"
        )
        self.assertEqual(
            i.curkey,
            "http://user.qzone.qq.com/1111111111/mood/1d5bbd5344bd435e2dd90d00"
        )
