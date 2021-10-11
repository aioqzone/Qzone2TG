from abc import ABC, abstractmethod, abstractproperty

from qzone.parser import QzJsonParser as Feed


class ContentExtracter(ABC):
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    @abstractmethod
    def msg(self):
        return self.feed.parseText()

    @abstractmethod
    def forward(self):
        return self.feed.parseForward()[-1]

    def img(self):
        return self.feed.parseImage()

    def video(self):
        return self.feed.parseVideo()

    def content(self):
        return self.img(), self.forward(), self.img()

    @abstractproperty
    def isBlocked(self):
        return False
