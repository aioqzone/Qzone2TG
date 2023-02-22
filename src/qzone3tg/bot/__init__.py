"""This package contains some essential customizations for :external:mod:`telegram.bot`."""

from typing import TypeVar

from telegram import InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from telegram._utils.types import ReplyMarkup

ChatId = str | int
SupportMedia = InputMediaAnimation | InputMediaDocument | InputMediaPhoto | InputMediaVideo
"""Supported media types to be sent."""
GroupMedia = InputMediaDocument | InputMediaPhoto | InputMediaVideo
"""Supported group media types."""
MD = TypeVar("MD", InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo)
