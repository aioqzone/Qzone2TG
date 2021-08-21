from abc import ABC, abstractmethod
from typing import Callable


class QREvent(ABC):
    _resend = None

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

    def register_resend_callback(self, resend_callback: Callable[[], bytes]):
        self._resend = resend_callback


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
    def fetchEnd(self):
        pass

    @abstractmethod
    def fetchError(self):
        pass


class FeedEvent(ABC):
    def contentReady(self, msg: str, forward: str, img: list, *args, **kwargs):
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

    def loginSuccessed(self, *args, **kwargs):
        pass

    def loginFailed(self, *args, **kwargs):
        pass

    def pageFetched(self, *args, **kwargs):
        pass

    def fetchEnd(self, *args, **kwargs):
        pass

    def fetchError(self, msg, *args, **kwargs):
        pass

    def contentReady(self, msg: str, forward: str, img: list, *args, **kwargs):
        return super().contentReady(msg, forward, img, *args, **kwargs)
