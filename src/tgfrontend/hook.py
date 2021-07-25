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


class TgUiHook(QREvent, QzoneEvent):
    pass
