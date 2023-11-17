from __future__ import annotations

import typing as t

from tylisten import hookdef

if t.TYPE_CHECKING:
    from aiogram.types import InlineKeyboardButton
    from aioqzone_feed.type import FeedContent


@hookdef
def is_uin_blocked(uin: int) -> bool:
    return False


@hookdef
def inline_buttons(feed: FeedContent) -> InlineKeyboardButton | None:
    return None
