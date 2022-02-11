from aioqzone_feed.type import BaseFeed
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class FeedOrm(Base):    # type: ignore
    __tablename__ = 'feed'

    fid = sa.Column(sa.VARCHAR, nullable=False, index=True)
    uin = sa.Column(sa.Integer, primary_key=True)
    abstime = sa.Column(sa.Integer, primary_key=True)
    appid = sa.Column(sa.Integer, nullable=False)
    typeid = sa.Column(sa.Integer, nullable=True)
    nickname = sa.Column(sa.VARCHAR, default='Unknown', nullable=False)
    curkey = sa.Column(sa.VARCHAR, nullable=True)
    unikey = sa.Column(sa.VARCHAR, nullable=True)
    mids = sa.Column(sa.PickleType(), nullable=True)
    """message_id list, as a pickle type"""
    @classmethod
    def from_base(cls, obj: BaseFeed, mids: list[int] = None):
        return cls(
            fid=obj.fid,
            uin=obj.uin,
            abstime=obj.abstime,
            appid=obj.appid,
            typeid=obj.typeid,
            nickname=obj.nickname,
            curkey=obj.curkey and str(obj.curkey),
            unikey=obj.unikey and str(obj.unikey),
            mids=mids
        )

    @staticmethod
    def set_by(record: 'FeedOrm', obj: BaseFeed, mids: list[int] = None):
        assert record.fid == obj.fid
        assert record.uin == obj.uin
        assert record.abstime == obj.abstime
        record.appid = obj.appid
        record.typeid = obj.typeid
        record.nickname = obj.nickname
        record.curkey = obj.curkey and str(obj.curkey)
        record.unikey = obj.unikey and str(obj.unikey)
        record.mids = mids


class CookieOrm(Base):    # type: ignore
    __tablename__ = 'cookie'

    uin = sa.Column(sa.Integer, primary_key=True)
    cookie = sa.Column(sa.PickleType())
