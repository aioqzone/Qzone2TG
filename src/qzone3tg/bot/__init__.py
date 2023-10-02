"""This package contains some essential customizations for :external:mod:`telegram.bot`."""

from typing import TypeVar

from aiogram.types.inline_keyboard_markup import InlineKeyboardMarkup
from aiogram.types.input_media_animation import InputMediaAnimation
from aiogram.types.input_media_document import InputMediaDocument
from aiogram.types.input_media_photo import InputMediaPhoto
from aiogram.types.input_media_video import InputMediaVideo

ChatId = str | int
SupportMedia = InputMediaAnimation | InputMediaDocument | InputMediaPhoto | InputMediaVideo
"""Supported media types to be sent."""
ReplyMarkup = InlineKeyboardMarkup

MD = TypeVar("MD", InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo)
