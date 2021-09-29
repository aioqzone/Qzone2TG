import logging
import re
from datetime import datetime
from typing import Iterable, Optional, Union
from pytz import timezone

from lxml.html import HtmlElement
from qzemoji import query, resolve

HTML_ENTITY = {
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
}
TIME_ZONE = timezone('Asia/Shanghai')

logger = logging.getLogger(__name__)


def subHtmlEntity(txt: Optional[str]):
    if txt is None: return ''
    return re.sub('[<>&]', lambda m: HTML_ENTITY[m.group(0)], txt)


def url2unicode(src: str):
    try:
        m = query(resolve(src))
        if m is None: return ""
        return f"[/{m}]"
    except ValueError:
        logger.warning('cannot resolve emoji: ' + src)
        return ""


def elm2txt(elm: Union[HtmlElement, Iterable[HtmlElement]], richText=True) -> str:
    """
    elm: Iterable[HtmlElement]
    """
    txt = subHtmlEntity(elm.text) if isinstance(elm, HtmlElement) else ''

    hd = lambda i: (f"<b>{elm2txt(i)}</b>" if richText else elm2txt(i)) + '\n'
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


def sementicTime(timestamp: int):
    feedtime = datetime.fromtimestamp(timestamp, TIME_ZONE)
    d = datetime.now(TIME_ZONE) - feedtime
    ch = ['', '昨天 ', '前天 ']
    s = ''
    if d.days <= 2: s += ch[d.days]
    else: s += feedtime.strftime('%m月%d日 ')
    s += feedtime.strftime('%H:%M')
    return s
