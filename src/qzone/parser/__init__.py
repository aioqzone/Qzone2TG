import logging
import re
from pathlib import PurePath
from typing import Callable, Dict, List, Optional, Text, Tuple
from urllib.parse import urlparse

from lxml.html import HtmlElement, fromstring, tostring
from middleware.utils import sementicTime
from utils.decorator import cached
from utils.iterutils import find_if

from .html.imgitem import ImageItem
from .html.txtbox import Txtbox

logger = logging.getLogger(__name__)


class QzHtmlParser:
    class f:
        ct = '//div[starts-with(@class,"f-ct")]'
        single_content = '//div[starts-with(@class,"f-single-content")]'
        info = single_content + '//div[starts-with(@class,"f-info")]'
        single_foot = '//div[@class="f-single-foot"]'

    def __init__(self, html: str) -> None:
        self.src = html

    def _x(self, *args) -> List[HtmlElement]:
        return self.src.xpath(''.join(args))

    @staticmethod
    def trans(html: str):
        return re.sub(
            r"\\{1,2}x([\dA-F]{2})", lambda m: chr(int(m.group(1), 16)), html.strip()
        )

    @property
    def src(self):
        return self._src

    @src.setter
    def src(self, html: str):
        self._src: HtmlElement = fromstring(html)
        del self.feedData, self.likeData

    def parseText(self) -> str:
        elm: list = self._x(
            self.f.single_content, '//div[starts-with(@class,"f-info")]'
        )
        if not elm: return ""
        elif len(elm) == 1: elm = elm.pop()
        elif len(elm) == 2: elm = max(elm, key=len)
        elm = self._x(self.f.single_content,
                      f'//div[@class="{elm.attrib["class"]}"]')[0]
        return str(Txtbox(elm))

    @property
    def unikey(self):
        return self.likeData['unikey']

    @property
    def curkey(self):
        return self.likeData['curkey']

    @property
    def isLike(self):
        return '1' in self.likeData['islike']

    def parseBio(self) -> Optional[str]:
        bio = self._x('//div[@class="user-pto"]/a/img/@src')
        if bio: return bio[0]

    def parseVideo(self) -> List[str]:
        CANNOT = ['.swf']
        ext = lambda url: PurePath(urlparse(url).path).suffix
        video = self._x(self.f.ct, '//div[contains(@class,"f-video-wrap")]')
        media = []
        for i in video:
            url = i.attrib['url3']
            if ext(url) not in CANNOT:
                media.append(url)
                continue

            cover = self._x(
                self.f.ct, f'//div[@url3="{url}"]', '/div[@class="video-img"]',
                '/img/@src'
            )
            if cover: media.append(cover[0])
            else:
                logger.warning('Cannot get video album: url=' + url)
        return media

    @cached
    def feedData(self) -> Dict[str, str]:
        elm = self._x('//i[@name="feed_data"]')
        elm = elm[0].attrib
        if elm:
            return {k[5:]: v for k, v in elm.items() if k.startswith("data-")}
        else:
            logger.warning('cannot parse i@name="feed_data"')
            return {}

    def parseLikeList(self) -> List[str]:
        return [
            tostring(i, encoding='utf-8').decode('utf-8')
            for i in self._x(self.f.single_foot, '//div[@class="user-list"]')
        ]

    def parseComments(self) -> List[str]:
        return [
            tostring(i, encoding='utf-8').decode('utf-8') for i in
            self._x('//div[@class="mod-comments"]', '/div[@class="comments-list "]')
        ]

    @cached
    def likeData(self):
        """
        dict contains (islike, likecnt, showcount, unikey, curkey, ...)
        """
        att: Dict[str, str] = (
            self._x(self.f.single_foot, '//a[contains(@class,"qz_like_prase")]') +
            self._x(self.f.single_foot, '//a[contains(@class,"qz_like_btn_v3 ")]')
        )[0].attrib
        assert att
        return {k[5:]: v for k, v in att.items() if k.startswith('data-')}

    def parseForward(self) -> Tuple[Optional[str], Optional[str], str]:
        """parse forwarder

        Returns:
            tuple: nickname, org link, text
        """
        ls: HtmlElement = self._x(self.f.ct, '//div[starts-with(@class,"txt-box")]')
        if not ls: return
        if len(ls) == 1: txtbox = ls.pop()
        elif len(ls) == 2: txtbox = max(ls, key=lambda e: len(e))

        nick = link = None
        safe_cls = lambda a: a.attrib.get('class', '')

        txtbox = list(txtbox)
        for i, a in enumerate(txtbox):
            if not isinstance(a, HtmlElement): continue

            if a.tag == 'div' and safe_cls(a).startswith('brand-name'):
                if (ia := find_if(
                        a, lambda i: safe_cls(i).startswith('nickname'))) is not None:
                    link = ia.attrib['href']
                    nick = ia.text.strip()
                    txtbox[i] = a.tail or ""
            elif a.tag == 'a' and safe_cls(a).startswith('nickname'):
                link = a.attrib['href']
                nick = a.text.strip()
                txtbox[i] = a.tail or ""

        txt = str(Txtbox(txtbox)).strip().lstrip('：')
        return nick, link, txt

    def isCut(self):
        txt: list = self._x(self.f.info, '//a[@data-cmd="qz_toggle"]')
        return bool(txt)


class QzJsonParser(QzHtmlParser):
    def __init__(self, feed):
        assert isinstance(feed, dict)
        feed['html'] = QzHtmlParser.trans(feed['html'])
        self.raw = feed
        super().__init__(feed['html'])

    @property
    def html(self):
        return self.raw['html']

    @html.setter
    def html(self, html: str):
        self.raw['html'] = html
        self.src = html

    def parseImage(
        self, get_raw_cb: Callable[[dict, int], List[Dict[str, str]]] = None
    ):
        img = self._x(self.f.ct, '//a[@class="img-item  "]')
        img = [ImageItem(self.uin, i) for i in img]

        if not get_raw_cb: return list(filter(None, (i.src for i in img)))
        if not img: return []

        first = img[0]
        if not first.hasAlbum(): return []
        r = get_raw_cb(first.data, len(img))

        if len(r) < len(img):
            logging.error('Getting origin photo error')
            return list(filter(None, (i.src for i in img)))
        return [i['url'] for i in r]

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
        return sementicTime(self.abstime)

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
            'unikey': self.unikey,
            'curkey': self.curkey,
            'appid': self.appid,
            'typeid': self.typeid,
            'key': self.feedkey,
        }

    def __hash__(self) -> int:
        return int(self.feedkey, 16)

    def __repr__(self) -> str:
        return f"{self.nickname}, {self.feedstime}"
