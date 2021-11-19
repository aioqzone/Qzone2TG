import logging
import re
from typing import Optional

from lxml.html import HtmlElement

logger = logging.getLogger(__name__)


class ImageItem:
    def __init__(self, img_item: HtmlElement) -> None:
        need = ['topicid', 'pickey', 'param', 'width', 'height']
        d = dict(img_item.attrib)
        self.data = {k: d['data-' + k] for k in need if 'data-' + k in d}
        self.elm = img_item

    def innerImg(self) -> Optional[HtmlElement]:
        for i in self.elm:
            if i.tag == 'img': return i

    def hasAlbum(self):
        return 'topicid' in self.data and 'pickey' in self.data

    @property
    def src(self) -> Optional[str]:
        i = self.innerImg()
        if i is None: return

        src = i.get('src', '')
        if src.startswith('http'):
            return src

        src = re.search(r"trueSrc:'(http.*?)'", i.attrib['onload'])
        if src:
            return src.group(1).replace('\\', '')

        if 'onload' in i.attrib:
            logger.warning('cannot parse @onload: ' + i.attrib['onload'])
        else:
            logger.warning('cannot parse @src: ' + i.attrib['src'])

    @src.setter
    def src(self, url: str):
        i = self.innerImg()
        if i is None: return
        i.attrib['src'] = url
