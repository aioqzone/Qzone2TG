import logging
import re
from typing import Iterable, Optional, TypeVar, Union

from lxml.html import HtmlElement
from qzemoji import query, resolve

logger = logging.getLogger(__name__)
Html = TypeVar('Html', HtmlElement, str)

HTML_ENTITY = {
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
}


def subHtmlEntity(txt: Optional[str]):
    if txt is None: return ''
    return re.sub('[<>&]', lambda m: HTML_ENTITY[m.group(0)], txt)


class Txtbox:
    br = '\n'

    def __init__(self, elm: Union[HtmlElement, Iterable[Html]], rich=True) -> None:
        self.elm = elm
        self.rich = rich
        self._mkswitch()

    def _mkswitch(self):
        hd = lambda i: (
            f"<b>{Txtbox(i, True)}</b>" if self.rich else str(Txtbox(i))
        ) + self.br
        switch = {f'h{i + 1}': hd for i in range(6)}
        switch.update(
            br=lambda i: self.br,
            img=lambda i: self.l2u(i.attrib['src']),
            div=lambda i: str(Txtbox(i, self.rich)),
            span=lambda i: str(Txtbox(i, self.rich)),
            a=lambda i: '' if i.attrib['href'].startswith("javascript") else
            f'<a href="{i.attrib["href"]}">{subHtmlEntity(i.text)}</a>'
            if self.rich else subHtmlEntity(i.text)
        )
        self.switch = switch

    @staticmethod
    def l2u(src: str):
        try:
            m = query(resolve(src))
            return f"[/{m or '表情'}]"
        except ValueError:
            logger.warning('cannot resolve emoji: ' + src)
            return ""

    def __str__(self):
        elm = self.elm
        switch = self.switch

        txt = subHtmlEntity(elm.text) if isinstance(elm, HtmlElement) else ''
        for i in elm:
            if not isinstance(i, HtmlElement):
                txt += subHtmlEntity(i)
                continue
            if i.tag in switch:
                txt += switch[i.tag](i) + subHtmlEntity(i.tail)
            else:
                logger.warning("cannot recognize tag: " + i.tag)
        return txt
