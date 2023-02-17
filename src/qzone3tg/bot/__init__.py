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
SupportMedia = InputMediaAnimation | InputMediaDocument | InputMediaPhoto | InputMediaVideo
GroupMedia = InputMediaDocument | InputMediaPhoto | InputMediaVideo
MD = TypeVar("MD", InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo)
ReplyMarkup = ReplyKeyboardMarkup | ForceReply
