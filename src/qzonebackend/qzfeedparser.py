import logging
import re

import yaml
from lxml.html import HtmlElement, fromstring, tostring

logger = logging.getLogger("Qzone HTML Parser")

afmt = "<a src={src}>{text}</a>"
face = emoji = None
with open("misc/qq_face.yaml") as f:
    face = yaml.safe_load(f)
with open("misc/emoji.yaml") as f:
    emoji = yaml.safe_load(f)


def transEmoji(name: str) -> str:
    if name.endswith(".png"):
        return face.get(name, "[/表情]")
    elif name.endswith(".gif"):
        if name in emoji:
            return emoji[name]
        else:
            logger.warning('new gif: ' + name)
            return "[/表情]"


def url2unicode(m: re.Match):
    return "" if m is None else transEmoji(m.group(1))


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
                txt += afmt.format(
                    src=i.attrib['href'], text=i.text
                ) if richText else i.text
        else:
            logger.warning("cannot recognize tag: " + i.tag)
    return txt


def find_if(iter: list, pred):
    for i in iter:
        if pred(i): return i


class QZFeedParser:
    def __init__(self, feed):
        assert isinstance(feed, dict)
        self.raw = feed
        self.src: HtmlElement = fromstring(feed['html'])

    def parseText(self) -> str:
        elm: list = self.src.xpath(
            '//div[starts-with(@class,"f-single-content")]//div[starts-with(@class,"f-info")]'
        )
        if not elm: return ""
        elif len(elm) == 1: elm = elm.pop()
        elif len(elm) == 2: elm = max(elm, key=lambda e: len(e))
        return elm2txt(
            self.src.xpath(
                '//div[starts-with(@class,"f-single-content")]//div[@class="%s"]/node()'
                % elm.attrib['class']
            )
        )

    @property
    def nickname(self) -> str:
        return self.raw['nickname']

    @property
    def feedstime(self) -> str:
        return self.raw['feedstime'].strip()

    @property
    def uckeys(self) -> tuple:
        return self.parseLikeData()[-2:]

    @property
    def appid(self) -> int:
        return int(self.raw['appid'])

    @property
    def typeid(self) -> int:
        return int(self.raw['typeid'])

    @property
    def feedkey(self) -> str:
        return self.raw['key']

    @property
    def isLike(self) -> bool:
        return self.parseLikeData()[0]

    def parseBio(self) -> str:
        return self.src.xpath('//div[@class="user-pto"]/a/img/@src')[0]

    def parseImage(self) -> list:
        return self.src.xpath('//div[@class="f-ct "]//a[@class="img-item  "]/img/@src')

    def parseForward(self) -> tuple:
        ls: list = self.src.xpath(
            '//div[@class="f-ct "]//div[starts-with(@class,"txt-box")]'
        )
        if not ls: return
        elif len(ls) == 1: ls = ls.pop()
        elif len(ls) == 2: ls = max(ls, key=lambda e: len(e))
        ls = self.src.xpath(
            '//div[@class="f-ct "]//div[@class="%s"]/node()' % ls.attrib['class']
        )
        for i in range(len(ls)):
            a = ls.pop(0)
            if isinstance(a, HtmlElement):
                if a.tag == 'div' and a.attrib['class'].startswith('brand-name'):
                    a = find_if(a, lambda i: i.attrib['class'].startswith('nickname'))
                if a.tag == 'a' and a.attrib['class'].startswith('nickname'):
                    link = a.attrib['href']
                    nick = a.text.strip()
                    break

        if not ls: return
        ls: str = elm2txt(ls)
        ls = ls.strip('：').strip()
        return nick, link, ls

    def isCut(self) -> bool:
        txt: list = self.src.xpath(
            '//div[starts-with(@class,"f-single-content")]\
            //div[starts-with(@class,"f-info")]//\
            a[@data-cmd="qz_toggle"]'
        )
        return bool(txt)

    def parseFeedData(self) -> dict:
        # 说实话这个好像没啥用
        elm = self.src.xpath('//i[@name="feed_data"]')
        if not elm: return
        else: elm = elm[0]
        elm: dict = elm.attrib
        return {k[5:]: v for k, v in elm.items() if k.startswith("data-")}

    def parseLikeList(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8') for i in
            self.src.xpath('//div[@class="f-single-foot"]//div[@class="user-list"]')
        ]

    def parseComments(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8') for i in
            self.src.xpath('//div[@class="mod-comments"]/div[@class="comments-list "]')
        ]

    def parseLikeData(self):
        """
        return (islike, likecnt, showcnt, unikey, curkey)
        """
        att: dict = self.src.xpath(
            '//div[@class="f-single-foot"]//a[@class="praise qz_like_prase"]'
        )[0].attrib
        assert att
        return att['data-islike'], att['data-likecnt'], att['data-showcount'], att[
            'data-unikey'], att['data-curkey']
