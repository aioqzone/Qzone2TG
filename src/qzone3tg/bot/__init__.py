"""This package contains some essential customizations for :external:mod:`telegram.bot`."""

from typing import Protocol, TypeVar

from telegram import (
    ForceReply,
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    ReplyKeyboardMarkup,
)

ChatId = str | int
InputMedia = InputMediaAnimation | InputMediaDocument | InputMediaPhoto | InputMediaVideo
MD = TypeVar("MD", InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo)
ReplyMarkup = ReplyKeyboardMarkup | ForceReply


class BotProtocol(Protocol):
    """A protocol to say what a bot must do.
    This is designed according to :class:`telegram.Bot`。"""

    async def send_message(self, to: ChatId, text: str, **kw) -> Message:
        """A bot can send message."""
        ...

    async def send_photo(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        """A bot can send photo."""
        ...

    async def send_animation(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        """A bot can send animation."""
        ...

    async def send_document(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        """A bot can send document."""
        ...

    async def send_video(self, to: ChatId, media: str | bytes, text: str, **kw) -> Message:
        """A bot can send video."""
        ...

    async def edit_message_media(self, to: ChatId, mid: int, media: InputMedia) -> Message | bool:
        """A bot can edit the media it has sent before."""
        ...

    async def send_media_group(self, to: ChatId, media: list[InputMedia], **kw) -> list[Message]:
        """A bot can send a group of media."""
        ...
