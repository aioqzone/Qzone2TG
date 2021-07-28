from abc import ABC, abstractmethod


class QREvent(ABC):
    @abstractmethod
    def QrFetched(self):
        pass

    @abstractmethod
    def QrSent(self):
        pass

    @abstractmethod
    def QrScanSucceessed(self):
        pass

    @abstractmethod
    def QrExpired(self):
        pass


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


class NullUI(QREvent, QzoneEvent):
    def QrFetched(self, png: bytes, *args, **kwargs):
        pass

    def QrSent(self, *args, **kwargs):
        pass

    def QrScanSucceessed(self, *args, **kwargs):
        pass

    def QrExpired(self, *args, **kwargs):
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
