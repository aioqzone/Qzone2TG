from aioqzone_feed.type import FeedContent, VisualMedia
from pydantic import BaseModel, HttpUrl
from telegram import Message

from qzone3tg.bot import BotProtocol, ChatId


class FakeBot(BotProtocol):
    def __init__(self) -> None:
        self.log = []

    def send_message(self, chat_id: ChatId, text: str, **kw):
        self.log.append(("message", chat_id, text, kw))
        return fake_message(len(self.log))

    def send_photo(self, chat_id: ChatId, photo: str | bytes, caption: str, **kw):
        self.log.append(("photo", chat_id, photo, caption, kw))
        return fake_message(len(self.log))

    def send_media_group(self, chat_id: ChatId, media: list, **kw):
        self.log.append(("group", chat_id, media, kw))
        return fake_message(len(self.log))

    def edit_message_media(self, to: ChatId, mid: int, media):
        self.log.append(("edit_photo", to, mid, media))
        return fake_message(len(self.log))


class Feed4Test(FeedContent):
    def __hash__(self) -> int:
        return hash(self.content)


def fake_message(id: int):
    m = object.__new__(Message)
    m.message_id = id
    return m


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
    return VisualMedia.construct(height=1, width=1, thumbnail=url, raw=url, is_video=False)
