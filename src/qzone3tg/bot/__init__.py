"""This package contains some essential customizations for :external:mod:`telegram.bot`."""

from typing import Protocol, TypeVar

from telegram import (
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

ChatId = str | int
InputMedia = InputMediaAnimation | InputMediaDocument | InputMediaPhoto | InputMediaVideo
MD = TypeVar("MD", InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo)


class BotProtocol(Protocol):
    async def send_message(self, to: ChatId, text: str, **kw) -> Message:
        ...

    async def send_photo(self, to: ChatId, photo: str | bytes, text: str, **kw) -> Message:
        ...

    async def send_animation(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        ...

    async def send_document(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        ...

    async def send_video(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        ...

    async def edit_message_media(self, to: ChatId, mid: int, media: InputMedia) -> Message | bool:
        ...

    async def send_media_group(self, to: ChatId, media: list[InputMedia], **kw) -> list[Message]:
        ...
