from datetime import datetime

from aioqzone.type.entity import TextEntity
from aioqzone_feed.type import FeedContent, VisualMedia
from pydantic import BaseModel, HttpUrl
from telegram import Chat, Message

from qzone3tg.bot import BotProtocol, ChatId


class FakeBot(BotProtocol):
    def __init__(self) -> None:
        self.log = []

    async def send_message(self, to: ChatId, text: str, **kw):
        self.log.append(("message", to, text, kw))
        return fake_message(len(self.log))

    async def send_photo(self, to: ChatId, media: str | bytes, caption: str, **kw):
        self.log.append(("photo", to, media, caption, kw))
        return fake_message(len(self.log))

    async def send_media_group(self, to: ChatId, media: list, **kw):
        self.log.append(("group", to, media, kw))
        return fake_message(len(self.log))

    async def edit_message_media(self, to: ChatId, mid: int, media):
        self.log.append(("edit_photo", to, mid, media))
        return fake_message(len(self.log))

    async def send_document(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        self.log.append(("document", to, media, text, kw))
        return fake_message(len(self.log))

    async def send_video(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        self.log.append(("video", to, media, text, kw))
        return fake_message(len(self.log))

    async def send_animation(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        self.log.append(("animation", to, media, text, kw))
        return fake_message(len(self.log))


class Feed4Test(FeedContent):
    def __hash__(self) -> int:
        return hash(str(self.entities))


def fake_message(id: int):
    return Message(id, datetime.now(), Chat(1, "private"))


def fake_feed(i: int | str) -> FeedContent:
    return Feed4Test.construct(
        entities=[TextEntity(type=2, con=str(i))],
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
