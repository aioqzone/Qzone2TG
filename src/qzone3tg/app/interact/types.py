from aiogram.filters.callback_data import CallbackData


class SerialCbData(CallbackData):
    command: str
    sub_command: str
