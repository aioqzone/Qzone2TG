import typing as t

from aiogram.filters.callback_data import CallbackData

MAX_CALLBACK_DATA: t.Final[int] = 64


class SerialCbData(CallbackData, prefix=""):
    command: str
    sub_command: str | None = None
