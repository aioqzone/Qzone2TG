import logging
import re

import yaml
from lxml.html import HtmlElement, fromstring, tostring
from utils import find_if

logger = logging.getLogger("Qzone HTML Parser")


class EmojiMgr:
    face_path = "misc/qq_face.yaml"
    emoji_path = "misc/emoji.yaml"
    singleton = None

    def __init__(self, face_path: str = None, emoji_path: str = None) -> None:
        if face_path: self.face_path = face_path
        if emoji_path: self.emoji_path = emoji_path
        self.loadEmoji()

    def loadEmoji(self):
        with open(self.face_path) as f:
            self.face = yaml.safe_load(f)
        with open(self.emoji_path) as f:
            self.emoji = yaml.safe_load(f)

    def transEmoji(self, name: str) -> str:
        if name.endswith(".png"):
            return self.face.get(name, "[/表情]")
        elif name.endswith(".gif"):
            if name in self.emoji:
                return self.emoji[name]
            else:
                logger.warning('new gif: ' + name)
                return "[/表情]"

    def __getitem__(self, name):
        return self.transEmoji(name)

    @classmethod
    def factory(cls, *args, **kwargs):
        if cls.singleton is None:
            cls.singleton = cls(*args, **kwargs)
        return cls.singleton


def url2unicode(m: re.Match):
    return "" if m is None else EmojiMgr.factory().transEmoji(m.group(1))


def elm2txt(elm: list, richText=True) -> str:
    """
    elm: Iterable[HtmlElement]
    """
    faceurl = re.compile(r"http://qzonestyle.gtimg.cn/qzone/em/e(\d+\..*)")
    txt = ""
    for i in elm:
        if not isinstance(i, HtmlElement): txt += i
        elif i.tag == 'br': txt += '\n'
        elif i.tag == 'img':
            txt += url2unicode(faceurl.search(i.attrib['src']))
        elif i.tag == 'span':
            txt += elm2txt(i)
        elif i.tag == 'a':
            if not i.attrib['href'].startswith("javascript"):
                txt += f"<a src={i.attrib['href']}>{i.text}</a>" if richText else i.text
        else:
            logger.warning("cannot recognize tag: " + i.tag)
    return txt


class QZFeedParser:
    class f:
        ct = '//div[starts-with(@class,"f-ct")]'
        single_content = '//div[starts-with(@class,"f-single-content")]'
        info = single_content + '//div[starts-with(@class,"f-info")]'
        single_foot = '//div[@class="f-single-foot"]'

    def __init__(self, feed):
        assert isinstance(feed, dict)
        self.raw = feed
        self.src: HtmlElement = fromstring(feed['html'])
        self.raw['hash'] = self.__hash__()

    def updateHTML(self, html: str):
        self.src = fromstring(html)
        del self.feedData
        del self.likeData

    def parseText(self) -> str:
        elm: list = self.src.xpath(
            self.f.single_content + '//div[starts-with(@class,"f-info")]'
        )
        if not elm: return ""
        elif len(elm) == 1: elm = elm.pop()
        elif len(elm) == 2: elm = max(elm, key=lambda e: len(e))
        return elm2txt(
            self.src.xpath(
                self.f.single_content +
                '//div[@class="%s"]/node()' % elm.attrib['class']
            )
        )

    def dump(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            return yaml.safe_dump(self.raw, f) # TODO: maybe need to override the dumper

    @property
    def uin(self) -> int:
        return int(self.raw['uin'])

    @property
    def hash(self) -> int:
        return self.raw['hash']

    @property
    def nickname(self) -> str:
        return self.raw['nickname']

    @property
    def feedstime(self) -> str:
        return self.raw['feedstime'].strip()

    @property
    def uckeys(self) -> tuple:
        self.parseLikeData()
        return self.likeData['unikey'], self.likeData['curkey']

    @property
    def appid(self) -> int:
        return int(self.raw['appid'])

    @property
    def typeid(self) -> int:
        return int(self.raw['typeid'])

    @property
    def fid(self) -> str:
        return self.raw['key']

    @property
    def feedkey(self) -> str:
        return self.raw['key']

    @property
    def abstime(self) -> int:
        return int(self.raw['abstime'])

    @property
    def isLike(self) -> bool:
        return '1' in self.parseLikeData()['islike']

    def parseBio(self) -> str:
        return self.src.xpath('//div[@class="user-pto"]/a/img/@src')[0]

    def parseImage(self) -> list:
        return self.src.xpath(self.f.ct + '//a[@class="img-item  "]/img/@src')

    def parseForward(self) -> tuple:
        """parse forwarder

        Returns:
            tuple: nickname, org link, text
        """
        ls: list = self.src.xpath(self.f.ct + '//div[starts-with(@class,"txt-box")]')
        if not ls: return
        elif len(ls) == 1: ls = ls.pop()
        elif len(ls) == 2: ls = max(ls, key=lambda e: len(e))
        ls = self.src.xpath(
            self.f.ct + '//div[@class="%s"]/node()' % ls.attrib['class']
        )
        for a in ls:
            if not isinstance(a, HtmlElement): continue

            if a.tag == 'div' and a.attrib['class'].startswith('brand-name'):
                a = find_if(a, lambda i: i.attrib['class'].startswith('nickname'))
            elif a.tag == 'a' and a.attrib['class'].startswith('nickname'):
                link = a.attrib['href']
                nick = a.text.strip()
                break
        else:
            return

        ls: str = elm2txt(ls)
        ls = ls.strip('：').strip()
        return nick, link, ls

    def isCut(self) -> bool:
        txt: list = self.src.xpath(self.f.info + '//a[@data-cmd="qz_toggle"]')
        return bool(txt)

    def parseFeedData(self) -> dict:
        # 说实话这个好像没啥用
        if not hasattr(self, 'feedData'):
            elm = self.src.xpath('//i[@name="feed_data"]')[0].attrib
            assert elm
            self.feedData = {k[5:]: v for k, v in elm.items() if k.startswith("data-")}
        return self.feedData

    def parseLikeList(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8')
            for i in self.src.xpath(self.f.single_foot + '//div[@class="user-list"]')
        ]

    def parseComments(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8') for i in
            self.src.xpath('//div[@class="mod-comments"]/div[@class="comments-list "]')
        ]

    def parseLikeData(self):
        """
        dict contains (islike, likecnt, showcount, unikey, curkey, ...)
        """
        if not hasattr(self, 'likeData'):
            att: dict = self.src.xpath(
                self.f.single_foot + '//a[@class="praise qz_like_prase"]'
            )[0].attrib
            assert att
            self.likeData = {k[5:]: v for k, v in att.items() if k.startswith('data-')}

        return self.likeData

    def __hash__(self) -> int:
        return hash((self.uin, self.abstime))
