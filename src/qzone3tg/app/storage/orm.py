"""This module defines orms in this app."""


import sqlalchemy as sa
from aioqzone.model import FeedData, PersudoCurkey
from aioqzone_feed.type import BaseFeed
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column, relationship


class Base(MappedAsDataclass, DeclarativeBase):
    pass


class FeedOrm(Base):
    __tablename__ = "feed"

    fid: Mapped[str] = mapped_column(sa.VARCHAR)
    uin: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    abstime: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    appid: Mapped[int] = mapped_column(sa.Integer)
    curkey: Mapped[str | None] = mapped_column(sa.VARCHAR, nullable=True)
    unikey: Mapped[str | None] = mapped_column(sa.VARCHAR, nullable=True)
    typeid: Mapped[int] = mapped_column(sa.Integer, default=0)
    topicId: Mapped[str] = mapped_column(sa.VARCHAR, default="")
    nickname: Mapped[str] = mapped_column(sa.VARCHAR, default="Unknown")
    # mids: Mapped["MessageOrm"] = relationship()

    @classmethod
    def from_base(cls, obj: BaseFeed):
        return cls(
            fid=obj.fid,
            uin=obj.uin,
            abstime=obj.abstime,
            appid=obj.appid,
            typeid=obj.typeid,
            topicId=obj.topicId,
            nickname=obj.nickname,
            curkey=obj.curkey and str(obj.curkey),
            unikey=obj.unikey and str(obj.unikey),
        )

    @staticmethod
    def set_by(record: "FeedOrm", obj: BaseFeed):
        assert record.uin == obj.uin
        assert record.abstime == obj.abstime
        assert record.fid == obj.fid
        record.appid = obj.appid
        record.typeid = obj.typeid
        record.nickname = obj.nickname
        record.topicId = obj.topicId
        record.curkey = obj.curkey and str(obj.curkey)
        record.unikey = obj.unikey and str(obj.unikey)
        return record

    @classmethod
    def primkey(cls, feed: BaseFeed | PersudoCurkey | FeedData):
        match feed:
            case FeedData():
                return cls.uin == feed.userinfo.uin, cls.abstime == feed.abstime
            case BaseFeed() | FeedOrm() | PersudoCurkey():
                return cls.uin == feed.uin, cls.abstime == feed.abstime
            case _:
                raise TypeError(type(feed))

    def dict(self):
        return dict(
            fid=self.fid,
            uin=self.uin,
            abstime=self.abstime,
            appid=self.appid,
            typeid=self.typeid,
            topicId=self.topicId,
            nickname=self.nickname,
            curkey=self.curkey,
            unikey=self.unikey,
        )


class MessageOrm(Base):
    __tablename__ = "message"

    mid: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    uin: Mapped[int] = mapped_column(sa.ForeignKey("feed.uin"))
    abstime: Mapped[int] = mapped_column(sa.ForeignKey("feed.abstime"))

    @staticmethod
    def set_by(record: "MessageOrm", obj: BaseFeed, mid: int):
        record.mid = mid
        record.uin = obj.uin
        record.abstime = obj.abstime
        return record

    @classmethod
    def fkey(cls, feed: BaseFeed | FeedOrm):
        return cls.uin == feed.uin, cls.abstime == feed.abstime


class CookieOrm(Base):
    __tablename__ = "cookie"

    uin: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    p_skey: Mapped[str] = mapped_column(sa.VARCHAR)
    pt4_token: Mapped[str] = mapped_column(sa.VARCHAR)


class BlockOrm(Base):
    __tablename__ = "Block"

    uin: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
