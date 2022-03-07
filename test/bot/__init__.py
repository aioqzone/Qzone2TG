from aioqzone_feed.type import FeedContent
from aioqzone_feed.type import VisualMedia
from pydantic import BaseModel
from pydantic import HttpUrl

from qzone3tg.bot import BotProtocol
from qzone3tg.bot import ChatId


class FakeBot(BotProtocol):
    def __init__(self) -> None:
        self.log = []

    def send_message(self, to: ChatId, text: str, **kw):
        self.log.append(("message", to, text, kw))

    def send_photo(self, to: ChatId, photo: str | bytes, text: str, **kw):
        self.log.append(("photo", to, photo, text, kw))

    def send_media_group(self, to: ChatId, media: list, **kw):
        self.log.append(("group", to, media, kw))


class Feed4Test(FeedContent):
    def __hash__(self) -> int:
        return hash(self.content)


def fake_feed(i: int | str):
    return Feed4Test.construct(
        content=str(i) if isinstance(i, int) else i,
        appid=0,
        typeid=0,
        fid="",
        abstime=0,
        uin=0,
        nickname="",
    )


def fake_media(url: str):
    # fmt: off
    class W(BaseModel): u: HttpUrl
    url = W.parse_obj(dict(u=url)).u
    # fmt: on
    return VisualMedia.construct(
        height=1, width=1, thumbnail=url, raw=url, is_video=False
    )
