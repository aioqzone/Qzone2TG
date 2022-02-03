import asyncio
from typing import Any, Callable, Optional

from aioqzone_feed.type import BaseFeed
from pydantic import FilePath
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class FeedOrm(Base):    # type: ignore
    __tablename__ = 'feed'

    fid = sa.Column(sa.VARCHAR, primary_key=True, nullable=False)
    uin = sa.Column(sa.Integer, nullable=False, index=True)
    abstime = sa.Column(sa.Integer, primary_key=True, nullable=False, index=True)
    appid = sa.Column(sa.Integer, nullable=False)
    typeid = sa.Column(sa.Integer, nullable=True)
    nickname = sa.Column(sa.VARCHAR, default='Unknown', nullable=False)
    curkey = sa.Column(sa.VARCHAR, nullable=True)
    unikey = sa.Column(sa.VARCHAR, nullable=True)
    mids = sa.Column(sa.VARCHAR, nullable=True)
    """message_id list, as a comma-seperated string"""
    @classmethod
    def from_base(cls, obj: BaseFeed, mids: list[int] = None):
        return cls(
            fid=obj.fid,
            uin=obj.uin,
            abstime=obj.abstime,
            appid=obj.appid,
            typeid=obj.typeid,
            nickname=obj.nickname,
            curkey=obj.curkey,
            unikey=obj.unikey,
            mids=','.join(str(i) for i in mids) if mids else None
        )

    @staticmethod
    def set_by(record: 'FeedOrm', obj: BaseFeed, mids: list[int] = None):
        assert record.fid == obj.fid
        assert record.uin == obj.uin
        assert record.abstime == obj.abstime
        record.appid = obj.appid
        record.typeid = obj.typeid
        record.nickname = obj.nickname
        record.curkey = obj.curkey
        record.unikey = obj.unikey
        record.mids = ','.join(str(i) for i in mids) if mids else None


class FeedStore:
    """A class for feed storage with async support, using sqlite3 + sqlalchemy."""

    # sess: sessionmaker[AsyncSession]

    def __init__(self, database: FilePath = None, db_kwds: dict = None) -> None:
        db_kwds = db_kwds or {}
        if database is None: url = "sqlite+aiosqlite://"
        else: url = "sqlite+aiosqlite:///" + database.as_posix()
        self.engine = create_async_engine(url, **db_kwds)
        self.sess = sessionmaker(self.engine, class_=AsyncSession)

    async def close(self):
        await self.engine.dispose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def create(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(FeedOrm.metadata.create_all)

    async def save(self, feed: BaseFeed, mid_ls: list[int] = None, flush: bool = True):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param mid_ls: messages id list, defaults to None
        :param flush: commit at once, defaults to True
        """
        async with self.sess() as sess:
            async with sess.begin():
                result = await sess.execute(select(FeedOrm).where(FeedOrm.fid == feed.fid))
                if (prev := result.scalar()):
                    # if exist: update
                    FeedOrm.set_by(prev, feed, mid_ls)
                else:
                    # not exist: add
                    sess.add(FeedOrm.from_base(feed, mid_ls))
            if flush: await sess.commit()

    async def exists(self, fid: str) -> bool:
        """check if a feed exists in this database.

        :param feed: fid to check
        :return: whether exists
        """
        async with self.sess() as sess:
            stmt = select(FeedOrm).where(FeedOrm.fid == fid)
            result = await sess.execute(stmt)
        return result.first() is not None

    async def get_orm(self, *where) -> Optional[FeedOrm]:
        """Get a feed orm from database, with given criteria.

        :return: :class:`.FeedOrm`
        """
        async with self.sess() as sess:
            stmt = select(FeedOrm)
            if where: stmt = stmt.where(*where)
            result = await sess.execute(stmt)
        return result.scalar()

    async def get(self, *pred) -> Optional[tuple[BaseFeed, Optional[list[int]]]]:
        """Get a feed from database, with given criteria.
        If multiple records satisfy the criteria, returns the first.

        :return: :external:class:`aioqzone_feed.type.BaseFeed` and message ids, optional
        """
        if (orm := await self.get_orm(*pred)) is None: return
        return BaseFeed.from_orm(orm), [int(i) for i in orm.mids.split(',')] if orm.mids else None

    async def edit(self, callback: Callable[[FeedOrm], None], *where, flush: bool = True):
        """Edit a feed orm with given callback. Do NOTHING if no row selected.
        If multiple records satisfy the criteria, call with the first.

        :param callback: callback to modify a record.
        :return: :class:`.FeedOrm`
        """
        async with self.sess() as sess:
            stmt = select(FeedOrm)
            if where: stmt = stmt.where(*where)
            result = await sess.execute(stmt)
            orm = result.scalar()
            if orm is None: return
            callback(orm)
            if flush: await sess.commit()

    async def clean(self, seconds: float, timeout: float = None, flush: bool = True):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        :param timeout: timeout as that in :external:meth:`asyncio.wait`, defaults to None
        :param flush: commit at once, defaults to True
        :return: done, pending set as that in :external:meth:`asyncio.wait`
        :rtype: :obj:`Tuple[Set[Task], Set[Task]]`
        """
        from time import time
        if seconds <= 0: seconds += time()
        async with self.sess() as sess:
            async with sess.begin():
                result = await sess.execute(select(FeedOrm).where(FeedOrm.abstime < seconds))
                r = await asyncio.wait(
                    [sess.delete(i) for i in result.scalars()],
                    timeout=timeout,
                )
            if flush: await sess.commit()
            return r
