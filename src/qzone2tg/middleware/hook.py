from abc import ABC, abstractmethod
from typing import Callable


class QREvent(ABC):
    _resend = None
    _cancel = None

    @abstractmethod
    def QrFetched(self, png: bytes):
        pass

    @abstractmethod
    def QrFailed(self):
        pass

    @abstractmethod
    def QrScanSucceessed(self):
        pass

    @abstractmethod
    def QrExpired(self, new_png: bytes):
        pass

    @abstractmethod
    def QrCanceled(self):
        pass

    def register_resend_callback(self, resend_callback: Callable[[], bytes]):
        self._resend = resend_callback

    def register_cancel_callback(self, cancel_callback: Callable[[], None]):
        self._cancel = cancel_callback


class QzoneEvent(ABC):
    @abstractmethod
    def loginSuccessed(self):
        pass

    @abstractmethod
    def loginFailed(self):
        pass

    @abstractmethod
    def pageFetched(self):
        pass

    @abstractmethod
    def fetchError(self):
        pass


class FeedEvent(ABC):
    @abstractmethod
    def feedFetched(self, feed):
        pass

    @abstractmethod
    def allFetchEnd(self, sum: int):
        pass

    @abstractmethod
    def mediaUpdate(self, media: list):
        pass


class NullUI(QREvent, QzoneEvent, FeedEvent):
    def QrFetched(self, png: bytes, *args, **kwargs):
        pass

    def QrFailed(self, *args, **kwargs):
        pass

    def QrScanSucceessed(self, *args, **kwargs):
        pass

    def QrExpired(self, new_png: bytes, *args, **kwargs):
        pass

    def QrCanceled(self):
        pass

    def loginSuccessed(self, *args, **kwargs):
        pass

    def loginFailed(self, *args, **kwargs):
        pass

    def pageFetched(self, *args, **kwargs):
        pass

    def fetchError(self, msg, *args, **kwargs):
        pass

    def mediaUpdate(self, msg_ref: list, media: list):
        pass

    def feedFetched(self, feed):
        pass

    def allFetchEnd(self, sum: int):
        pass
