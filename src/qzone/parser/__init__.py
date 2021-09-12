import logging
import re
from typing import Optional

from lxml.html import HtmlElement, fromstring, tostring
from qzemoji import query
from utils.iterutils import find_if

logger = logging.getLogger(__name__)

HTML_ENTITY = {
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
}


def subHtmlEntity(txt: Optional[str]):
    if txt is None: return ''
    return re.sub('[<>&]', lambda m: HTML_ENTITY[m.group(0)], txt)


def url2unicode(src: str):
    m = re.search(r"http://qzonestyle.gtimg.cn/qzone/em/e(\d+\..*)", src)
    if m is None: return ""
    m = query(m.group(1))
    if m is None: return ""
    return f"[/{m}]"


def elm2txt(elm: HtmlElement, richText=True) -> str:
    """
    elm: Iterable[HtmlElement]
    """
    txt = subHtmlEntity(elm.text)

    hd = lambda i: f"<b>{elm2txt(i)}</b>" if richText else elm2txt(i)
    switch = {'h1': hd, 'h2': hd, 'h3': hd, 'h4': hd, 'h5': hd, 'h6': hd}
    switch.update(
        br=lambda i: '\n',
        img=lambda i: url2unicode(i.attrib['src']),
        div=lambda i: elm2txt(i, richText),
        span=lambda i: elm2txt(i, richText),
        a=lambda i: '' if i.attrib['href'].startswith("javascript") else
        f'<a href="{i.attrib["href"]}">{subHtmlEntity(i.text)}</a>'
        if richText else subHtmlEntity(i.text)
    )

    for i in elm:
        if not isinstance(i, HtmlElement):
            txt += subHtmlEntity(i)
            continue
        if i.tag in switch:
            txt += switch[i.tag](i) + subHtmlEntity(i.tail)
        else:
            logger.warning("cannot recognize tag: " + i.tag)
    return txt


class QZHtmlParser:
    class f:
        ct = '//div[starts-with(@class,"f-ct")]'
        single_content = '//div[starts-with(@class,"f-single-content")]'
        info = single_content + '//div[starts-with(@class,"f-info")]'
        single_foot = '//div[@class="f-single-foot"]'

    def __init__(self, html: str) -> None:
        self._src: HtmlElement = fromstring(html)

    def __x(self, *args):
        return self._src.xpath(''.join(args))

    @staticmethod
    def trans(html: str):
        return re.sub(
            r"\\{1,2}x([\dA-F]{2})", lambda m: chr(int(m.group(1), 16)), html.strip()
        )

    def updateHTML(self, html: str):
        self._src = fromstring(html)
        if hasattr(self, 'feedData'): del self.feedData
        if hasattr(self, 'likeData'): del self.likeData

    def parseText(self) -> str:
        elm: list = self.__x(
            self.f.single_content, '//div[starts-with(@class,"f-info")]'
        )
        if not elm: return ""
        elif len(elm) == 1: elm = elm.pop()
        elif len(elm) == 2: elm = max(elm, key=lambda e: len(e))
        return elm2txt(
            self.__x(self.f.single_content, f'//div[@class="{elm.attrib["class"]}"]')[0]
        )

    @property
    def uckeys(self) -> tuple:
        self.parseLikeData()
        return self.likeData['unikey'], self.likeData['curkey']

    @property
    def isLike(self) -> bool:
        return '1' in self.parseLikeData()['islike']

    def parseBio(self) -> str:
        return (bio := self.__x('//div[@class="user-pto"]/a/img/@src')) and bio[0]

    def parseImage(self):
        img = self.__x(self.f.ct, '//a[@class="img-item  "]/img')
        img = [
            (src := i.attrib['src']).startswith('http') and src
            or \
            (src := re.search(r"trueSrc:'(http.*?)'", i.attrib['onload'])) and
                src.group(1).replace('\\', '')
            or
            logger.warning('cannot parse @onload: ' + i.attrib['onload'])
            for i in img
        ]
        return [i.replace('rf=0-0', 'rf=viewer_311') for i in img if i]

    def parseFeedData(self) -> dict:
        if not hasattr(self, 'feedData'):
            elm = (elm := self.__x('//i[@name="feed_data"]')) and elm[0].attrib
            if elm:
                self.feedData = {
                    k[5:]: v
                    for k, v in elm.items() if k.startswith("data-")
                }
            else:
                logger.warning('cannot parse i@name="feed_data"')
                self.feedData = {}
        return self.feedData

    def parseLikeList(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8')
            for i in self.__x(self.f.single_foot, '//div[@class="user-list"]')
        ]

    def parseComments(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8') for i in
            self.__x('//div[@class="mod-comments"]', '/div[@class="comments-list "]')
        ]

    def parseLikeData(self):
        """
        dict contains (islike, likecnt, showcount, unikey, curkey, ...)
        """
        if not hasattr(self, 'likeData'):
            att: dict = (
                self.__x(self.f.single_foot, '//a[contains(@class,"qz_like_prase")]') +
                self.__x(self.f.single_foot, '//a[contains(@class,"qz_like_btn_v3 ")]')
            )[0].attrib
            assert att
            self.likeData = {k[5:]: v for k, v in att.items() if k.startswith('data-')}

        return self.likeData

    def parseForward(self) -> tuple:
        """parse forwarder

        Returns:
            tuple: nickname, org link, text
        """
        ls: HtmlElement = self.__x(self.f.ct, '//div[starts-with(@class,"txt-box")]')
        if not ls: return
        if len(ls) == 1: txtbox = ls.pop()
        elif len(ls) == 2: txtbox = max(ls, key=lambda e: len(e))

        nick = link = None
        for a in txtbox:
            if not isinstance(a, HtmlElement): continue

            if a.tag == 'div' and a.attrib['class'].startswith('brand-name'):
                if (a := find_if(a, lambda i: i.attrib['class'].startswith('nickname'))
                    ) is not None:
                    link = a.attrib['href']
                    nick = a.text.strip()
                    break
            elif a.tag == 'a' and a.attrib['class'].startswith('nickname'):
                link = a.attrib['href']
                nick = a.text.strip()
                break

        txt = elm2txt(txtbox).strip()
        return nick, link, txt

    def isCut(self) -> bool:
        txt: list = self.__x(self.f.info, '//a[@data-cmd="qz_toggle"]')
        return bool(txt)


class QZFeedParser(QZHtmlParser):
    def __init__(self, feed):
        assert isinstance(feed, dict)
        feed['html'] = QZHtmlParser.trans(feed['html'])
        self.raw = feed
        super().__init__(feed['html'])

    def updateHTML(self, html: str):
        self.raw['html'] = html
        return super().updateHTML(html)

    @property
    def uin(self) -> int:
        return int(self.raw['uin'])

    @property
    def hash(self) -> int:
        if 'hash' not in self.raw: self.raw['hash'] = self.__hash__()
        return self.raw['hash']

    @property
    def nickname(self) -> str:
        return self.raw['nickname']

    @property
    def feedstime(self) -> str:
        return self.raw['feedstime'].strip()

    @property
    def appid(self) -> int:
        return int(self.raw['appid'])

    @property
    def typeid(self) -> int:
        return int(self.raw['typeid'])

    @property
    def fid(self) -> str:
        return self.raw['key'] if 'key' in self.raw else self.raw['fid']

    @property
    def feedkey(self) -> str:
        return self.fid

    @property
    def abstime(self) -> int:
        return int(self.raw['abstime'])

    def getLikeId(self):
        return {
            'unikey': (uc := self.uckeys)[0],
            'curkey': uc[1],
            'appid': self.appid,
            'typeid': self.typeid,
            'key': self.feedkey,
        }

    def __hash__(self) -> int:
        return hash((self.uin, self.abstime))

    def __repr__(self) -> str:
        return f"{self.nickname}, {self.feedstime}"
