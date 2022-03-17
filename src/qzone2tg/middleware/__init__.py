from abc import ABC, abstractmethod, abstractproperty

from qzone2tg.qzone.parser import QzJsonParser as Feed


class ContentExtracter(ABC):
    blocked = set()

    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    @abstractmethod
    def msg(self):
        return self.feed.parseText()

    @abstractmethod
    def forward(self):
        return self.feed.parseForward()[-1]

    def img(self):
        i, f = self.feed.parseImage()
        try:
            if f.done(): return f.result()
        except:
            pass
        return i

    def video(self):
        return self.feed.parseVideo()

    def content(self):
        return self.img(), self.forward(), self.img()

    def prepare(self):
        cache = self.content()
        for k, v in {self.content: lambda: cache}.items():
            setattr(self, k.__name__, v)

    @property
    def imageFuture(self):
        return self.feed.img_future

    @abstractproperty
    def isBlocked(self):
        return self.feed.uin in self.blocked