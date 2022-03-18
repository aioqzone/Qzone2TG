"""This package contains some essential customizations for :external:mod:`telegram.bot`."""

from abc import ABC, abstractmethod

from telegram import InputMediaAnimation as Anim
from telegram import InputMediaDocument as Doc
from telegram import InputMediaPhoto as Pic
from telegram import InputMediaVideo as Video

ChatId = str | int
InputMedia = Pic | Video | Anim | Doc


class BotProtocol(ABC):
    @abstractmethod
    async def send_message(self, to: ChatId, text: str, **kw):
        pass

    @abstractmethod
    async def send_photo(self, to: ChatId, photo: str | bytes, text: str, **kw):
        pass

    @abstractmethod
    async def edit_message_media(self, to: ChatId, mid: int, media: InputMedia):
        pass
