from aiogram.filters.callback_data import CallbackData


class SerialCbData(CallbackData, prefix=""):
    command: str
    sub_command: str
