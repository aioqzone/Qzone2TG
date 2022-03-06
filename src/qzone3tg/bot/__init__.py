"""This package contains some essential customizations for :external:mod:`telegram.bot`."""

from abc import ABC
from abc import abstractmethod

ChatId = str | int


class BotProtocol(ABC):
    @abstractmethod
    async def send_message(self, to: ChatId, text: str, **kw):
        pass

    @abstractmethod
    async def send_photo(self, to: ChatId, photo: str | bytes, text: str, **kw):
        pass
