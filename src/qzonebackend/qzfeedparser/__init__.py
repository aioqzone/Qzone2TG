import logging
import re

import yaml
from lxml.html import HtmlElement, fromstring, tostring
from utils import find_if
from .emojimgr import url2unicode

logger = logging.getLogger("Qzone HTML Parser")


def elm2txt(elm: list, richText=True) -> str:
    """
    elm: Iterable[HtmlElement]
    """
    txt = ""
    for i in elm:
        if not isinstance(i, HtmlElement): txt += i
        elif i.tag == 'br': txt += '\n'
        elif i.tag == 'img':
            txt += url2unicode(i.attrib['src'])
        elif i.tag == 'span':
            txt += elm2txt(i)
        elif i.tag == 'a':
            if not i.attrib['href'].startswith("javascript"):
                if richText:
                    src = i.attrib['href']
                    txt += f'<a src="{src}">{i.text}</a>'
                else:
                    txt += i.text
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
        if hasattr(self, 'feedData'): del self.feedData
        if hasattr(self, 'likeData'): del self.likeData

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
        self.complete = True
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
                self.f.single_foot + '//a[contains(@class,"%s")]' %
                ('qz_like_btn_v3 ' if hasattr(self, 'complete') else 'qz_like_prase')
            )[0].attrib
            assert att
            self.likeData = {k[5:]: v for k, v in att.items() if k.startswith('data-')}

        return self.likeData

    def __hash__(self) -> int:
        return hash((self.uin, self.abstime))

    def __repr__(self) -> str:
        return f"{self.nickname}, {self.feedstime}"
