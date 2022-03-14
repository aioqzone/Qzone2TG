"""This module defines orms in this app."""

from typing import Callable, Generic, Optional, Type, TypeVar

import sqlalchemy as sa
from aioqzone_feed.type import BaseFeed
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
T = TypeVar("T")


class CommaList(Generic[T]):
    def __init__(
        self,
        cls: Type[T],
        tostr: Callable[[T], str] = str,
        toT: Callable[[bytes], T] | None = None,
    ) -> None:
        self.cls = cls
        self.tostr = tostr
        self.toT = toT or cls

    def dumps(self, obj: list[T], *args, **kwds):
        return ",".join(self.tostr(i) for i in obj).encode()

    def loads(self, commalist: bytes, *args, **kwds) -> list[T]:
        return [self.toT(i) for i in commalist.split(b",")]  # type: ignore


class FeedOrm(Base):  # type: ignore
    __tablename__ = "feed"

    fid = sa.Column(sa.VARCHAR, nullable=False)
    uin = sa.Column(sa.Integer, primary_key=True)
    abstime = sa.Column(sa.Integer, primary_key=True)
    appid = sa.Column(sa.Integer, nullable=False)
    typeid = sa.Column(sa.Integer, nullable=True)
    nickname = sa.Column(sa.VARCHAR, default="Unknown", nullable=False)
    curkey = sa.Column(sa.VARCHAR, nullable=True)
    unikey = sa.Column(sa.VARCHAR, nullable=True)
    mids: Optional[list[int]] = sa.Column(
        sa.PickleType(pickler=CommaList(int)), nullable=True  # type: ignore
    )
    """message_id list, as a pickle type"""

    @classmethod
    def from_base(cls, obj: BaseFeed, mids: list[int] | None = None):
        return cls(
            fid=obj.fid,
            uin=obj.uin,
            abstime=obj.abstime,
            appid=obj.appid,
            typeid=obj.typeid,
            nickname=obj.nickname,
            curkey=obj.curkey and str(obj.curkey),
            unikey=obj.unikey and str(obj.unikey),
            mids=mids,
        )

    @staticmethod
    def set_by(record: "FeedOrm", obj: BaseFeed, mids: list[int] | None = None):
        assert record.uin == obj.uin
        assert record.abstime == obj.abstime
        assert record.fid == obj.fid
        record.appid = obj.appid
        record.typeid = obj.typeid
        record.nickname = obj.nickname
        record.curkey = obj.curkey and str(obj.curkey)
        record.unikey = obj.unikey and str(obj.unikey)
        record.mids = mids

    @classmethod
    def primkey(cls, feed: BaseFeed):
        return cls.uin == feed.uin, cls.abstime == feed.abstime


class CookieOrm(Base):  # type: ignore
    __tablename__ = "cookie"

    uin = sa.Column(sa.Integer, primary_key=True)
    cookie = sa.Column(sa.PickleType())
