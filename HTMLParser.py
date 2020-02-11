import json
import logging
import re
from io import TextIOWrapper

from lxml.html import HtmlElement, fromstring, tostring

logger = logging.getLogger(__name__)

face = {}
with open("qq_face.json") as f:
    face = json.load(f)

def transEmoji(name: str):
    if name.endswith(".png"): 
        return face.get(name, "[/表情]")
    elif name.endswith(".gif"):
        logger.warning('new gif: ' + name)
        return "[/表情]"

def elm2txt(elm: list, richText = True)-> str:
    "elm: Iterable[HtmlElement]"
    faceurl = re.compile(r"http://qzonestyle.gtimg.cn/qzone/em/e(\d+\..*)")
    if richText: afmt = "<a src={src}>{text}</a>"
    txt = ""
    for i in elm:
        if not isinstance(i, HtmlElement): txt += i
        elif i.tag == 'br': txt += '\n'
        elif i.tag == 'img': 
            txt += HTMLParser.url2unicode(faceurl.search(i.attrib['src']))
        elif i.tag == 'span': txt += elm2txt(i)
        elif i.tag == 'a':
            if not i.attrib['href'].startswith("javascript"):
                txt += afmt.format(src = i.attrib['href'], text = i.text) if richText else i.text
        else: 
            logger.warning("cannot recognize tag: " + i.tag)
    return txt

def find_if(iter: list, pred):
    for i in iter: 
        if pred(i): return i

class HTMLParser:
    src: HtmlElement

    def __init__(self, HTML):
        if type(HTML) == str:
            self.src = fromstring(HTML)
        elif type(HTML) == TextIOWrapper:
            self.src = fromstring(HTML.read())
    
    def parseText(self)-> str:
        elm: list = self.src.xpath('//div[starts-with(@class,"f-single-content")]//div[starts-with(@class,"f-info")]')
        if not elm: return ""
        elif len(elm) == 1: elm = elm.pop()
        elif len(elm) == 2: elm = max(elm, key = lambda e: len(e))
        return elm2txt(self.src.xpath('//div[starts-with(@class,"f-single-content")]//div[@class="%s"]/node()' % elm.attrib['class']))

    def parseName(self)-> str:
        return self.src.xpath('//div[@class="user-info"]//a[@class="f-name q_namecard "]/text()')[0]

    def parseTime(self)-> str:
        return self.src.xpath('//div[@class="user-info"]//span[@class=" ui-mr8 state"]/text()')[0]
        
    def parseBio(self)-> str:
        return self.src.xpath('//div[@class="user-pto"]/a/img/@src')[0]

    def parseImage(self)-> list:
        return self.src.xpath('//div[@class="f-ct "]//a[@class="img-item  "]/img/@src')

    def parseForward(self)-> tuple:
        ls: list = self.src.xpath('//div[@class="f-ct "]//div[starts-with(@class,"txt-box")]')
        if not ls: return
        elif len(ls) == 1: ls = ls.pop()
        elif len(ls) == 2: ls = max(ls, key = lambda e: len(e))
        ls = self.src.xpath('//div[@class="f-ct "]//div[@class="%s"]/node()' % ls.attrib['class'])
        for i in range(len(ls)):
            a = ls.pop(0)
            if isinstance(a, HtmlElement) and a.tag == 'a' and a.attrib['class'].startswith('nickname'): 
                link = a.attrib['href']; nick = a.text.strip()
                break
        if not ls: return 
        ls.pop(0)
        return nick, link, elm2txt(ls)
        
    def hasNext(self)-> bool:
        txt: HtmlElement = self.src.xpath('//div[starts-with(@class,"f-single-content")]//a[@data-cmd="qz_toggle"]')
        if not txt: return False
        if txt[0].text == "展开全文": return True

    def parseFeedData(self)-> dict:
        elm = self.src.xpath('//i[@name="feed_data"]')
        if not elm: return
        else: elm = elm[0]
        elm: dict = elm.attrib
        return {k[5:]: v for k, v in elm.items() if k.startswith("data-")}

    def parseLikeList(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8') 
            for i in self.src.xpath('//div[@class="f-single-foot"]//div[@class="user-list"]')
        ]

    def parseComments(self):
        return [
            tostring(i, encoding='utf-8').decode('utf-8') 
            for i in self.src.xpath('//div[@class="mod-comments"]/div[@class="comments-list "]')
        ]

    def unikey(self):
        l = self.src.xpath('//div[@class="f-single-foot"]//@data-unikey')
        assert l
        return l[0]

    def curkey(self):
        l = self.src.xpath('//div[@class="f-single-foot"]//div[@class="icon-btn"]//@data-curkey')
        assert l
        return l[0]

    @staticmethod
    def url2unicode(m: re.Match):
        return "" if m is None else transEmoji(m.group(1))
