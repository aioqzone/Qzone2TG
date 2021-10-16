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


class QzCssHelper:
    def __init__(self, root: HtmlElement) -> None:
        self.root = root
        g = lambda l: l[0] if l else HtmlElement()
        self.fct: HtmlElement = g(root.cssselect('div.f-ct'))
        self.fsc: HtmlElement = g(root.cssselect('div.f-single-content'))
        self.ffoot: HtmlElement = g(root.cssselect('div.f-single-foot'))

        finfo = self.fsc.cssselect('div.f-info')
        if finfo:
            self.finfo: HtmlElement = max(finfo, key=len)
        else:
            self.finfo = HtmlElement()


class QzHtmlParser(QzCssHelper):
    def __init__(self, html: str) -> None:
        self.src = fromstring(html)
        self.dirty = False

    #### NOT USED YET
    def parseBio(self) -> Optional[str]:
        bio = self.root.cssselect('div.f-single-head div.user-pto a img')
        if bio: return bio[0].get('src')

    def parseLikeList(self) -> List[str]:
        return [
            tostring(i, encoding='utf-8').decode('utf-8')
            for i in self.ffoot.cssselect('div.user-list')
        ]

    def parseComments(self) -> List[str]:
        return [
            tostring(i, encoding='utf-8').decode('utf-8')
            for i in self.ffoot('div.mod-comments div.comments-list')
        ]

    #### NOT USED YET ####

    @staticmethod
    def trans(html: str):
        return re.sub(
            r"\\{1,2}x([\dA-F]{2})", lambda m: chr(int(m.group(1), 16)), html.strip()
        )

    @cached
    def src(self) -> HtmlElement:
        pass

    @src.setter
    def src(self, html: HtmlElement):
        del self.feedData, self.likeData
        super().__init__(html)

    def parseText(self) -> str:
        if self.finfo is None: return ""
        return str(Txtbox(self.finfo))

    @property
    def unikey(self):
        return self.likeData['unikey']

    @property
    def curkey(self):
        return self.likeData['curkey']

    @property
    def isLike(self):
        return '1' in self.likeData['islike']

    def _imageItems(self):
        img = self.fct.cssselect('a.img-item')
        return [ImageItem(i) for i in img]

    def parseImage(
        self, get_raw_cb: Callable[[dict, int], List[Dict[str, str]]] = None
    ):
        img = self._imageItems()
        if not img: return []

        default = list(filter(None, (i.src for i in img)))
        if not get_raw_cb: return default

        first = img[0]
        if not first.hasAlbum(): return default

        try:
            r = get_raw_cb(first.data, len(img))
        except:
            logger.warning("Error when getting raw images.", exc_info=True)
            return default

        if len(r) < len(img):
            logging.error('Getting origin photo error')
            return default

        raw = [i['url'] for i in r]
        for i, s in zip(img, raw):
            i.src = s
            self.dirty = True
        return raw

    def parseVideo(self) -> List[str]:
        CANNOT = ['.swf']
        ext = lambda url: PurePath(urlparse(url).path).suffix
        video = self.fct.cssselect('div.f-video-wrap')
        media = []
        for i in video:
            url = i.attrib['url3']
            if ext(url) not in CANNOT:
                media.append(url)
                continue

            cover = i.cssselect('div.video-img img')
            if cover: media.append(cover[0].get('src'))
            else:
                logger.warning('Cannot get video album: url=' + url)
        return media

    @cached
    def feedData(self) -> Dict[str, str]:
        elm = self.fsc.cssselect('i[name="feed_data"]')
        elm = elm[0].attrib
        if elm:
            return {k[5:]: v for k, v in elm.items() if k.startswith("data-")}
        else:
            logger.warning('cannot parse i@name="feed_data"')
            return {}

    @cached
    def likeData(self):
        """
        dict contains (islike, likecnt, showcount, unikey, curkey, ...)
        """

        att: Dict[str, str] = (
            self.ffoot.cssselect('a.qz_like_prase') +
            self.ffoot.cssselect('a.qz_like_btn_v3')
        )[0].attrib
        assert att
        return {k[5:]: v for k, v in att.items() if k.startswith('data-')}

    def parseForward(self) -> Optional[Tuple[Optional[str], Optional[str], str]]:
        """parse forwarder

        Returns:
            tuple: nickname, org link, text
        """
        ls: HtmlElement = self.fct.cssselect('div.txt-box')
        if not ls: return
        txtbox = max(ls, key=lambda e: len(e))

        nick = link = None
        safe_cls = lambda a: a.get('class', '')

        txtbox = list(txtbox)
        for i, a in enumerate(txtbox):
            if not isinstance(a, HtmlElement): continue

            if a.tag == 'div' and safe_cls(a).startswith('brand-name'):
                if (ia := find_if(
                        a, lambda i: safe_cls(i).startswith('nickname'))) is not None:
                    link = ia.get('href')
                    nick = ia.text.strip()
                    txtbox[i] = a.tail or ""
            elif a.tag == 'a' and safe_cls(a).startswith('nickname'):
                link = a.get('href')
                nick = a.text.strip()
                txtbox[i] = a.tail or ""

        txt = str(Txtbox(txtbox)).strip().lstrip('：')
        return nick, link, txt

    def isCut(self):
        txt: list = self.finfo.cssselect('a[data-cmd="qz_toggle"]')
        return bool(txt)

    def hasAlbum(self):
        if self.fct.cssselect('div.f-video-wrap'): return False

        items = self._imageItems()
        if not items: return False

        # return any(i.data['width'] > 600 or i.data['width'] > 600 for i in items)
        return True


class QzJsonParser(QzHtmlParser):
    def __init__(self, feed: dict):
        assert isinstance(feed, dict)
        self._raw = feed
        self.html = QzHtmlParser.trans(feed['html'])

    @property
    def html(self):
        if self.dirty:
            self._raw['html'] = tostring(self.root, encoding='utf-8').decode('utf-8')
            self.dirty = False
        return self._raw['html']

    @html.setter
    def html(self, html: str):
        self._raw['html'] = html
        super().__init__(html)

    @property
    def uin(self) -> int:
        return int(self._raw['uin'])

    @property
    def hash(self) -> int:
        if 'hash' not in self._raw: self._raw['hash'] = self.__hash__()
        return self._raw['hash']

    @property
    def nickname(self) -> str:
        return self._raw['nickname']

    @property
    def feedstime(self) -> str:
        return sementicTime(self.abstime)

    @property
    def appid(self) -> int:
        return int(self._raw['appid'])

    @property
    def typeid(self) -> int:
        return int(self._raw['typeid'])

    @property
    def fid(self) -> str:
        return self._raw['key'] if 'key' in self._raw else self._raw['fid']

    @property
    def feedkey(self) -> str:
        return self.fid

    @property
    def abstime(self) -> int:
        return int(self._raw['abstime'])

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
