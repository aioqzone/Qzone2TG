"""This package contains some essential customizations for :external:mod:`telegram.bot`."""

from typing import Final, TypeVar

from aiogram.types import (
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

ChatId = str | int
SupportMedia = InputMediaAnimation | InputMediaDocument | InputMediaPhoto | InputMediaVideo
"""Supported media types to be sent."""
ReplyMarkup = InlineKeyboardMarkup

MD = TypeVar("MD", InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo)

MAX_GROUP_MEDIA: Final[int] = 10
MAX_TEXT_LENGTH: Final[int] = 4096
CAPTION_LENGTH: Final[int] = 1024
LIM_TXT: Final[int] = MAX_TEXT_LENGTH - 1
LIM_MD_TXT: Final[int] = CAPTION_LENGTH - 1
