"""This module defines orms in this app."""


import sqlalchemy as sa
from aioqzone_feed.type import BaseFeed
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class FeedOrm(Base):
    __tablename__ = "feed"

    fid = sa.Column(sa.VARCHAR, nullable=False)
    uin = sa.Column(sa.Integer, primary_key=True)
    abstime = sa.Column(sa.Integer, primary_key=True)
    appid = sa.Column(sa.Integer, nullable=False)
    typeid = sa.Column(sa.Integer, nullable=False, default=0)
    topicId = sa.Column(sa.VARCHAR, nullable=False, default="")
    nickname = sa.Column(sa.VARCHAR, nullable=False, default="Unknown")
    curkey = sa.Column(sa.VARCHAR, nullable=True)
    unikey = sa.Column(sa.VARCHAR, nullable=True)

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
    def primkey(cls, feed: BaseFeed):
        return cls.uin == feed.uin, cls.abstime == feed.abstime


class MessageOrm(Base):
    __tablename__ = "message"

    mid = sa.Column(sa.Integer, primary_key=True)
    uin = sa.Column(sa.ForeignKey("feed.uin"))
    abstime = sa.Column(sa.ForeignKey("feed.abstime"))

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

    uin = sa.Column(sa.Integer, primary_key=True)
    cookie = sa.Column(sa.PickleType())
