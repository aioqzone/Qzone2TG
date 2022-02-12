import asyncio
from pathlib import Path
from typing import Optional, Union

from aioqzone.type import FeedRep
from aioqzone_feed.type import BaseFeed
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from ...bot.queue import StorageEvent
from .orm import FeedOrm


class AsyncEnginew:
    @classmethod
    def sqlite3(cls, path: Optional[Path], **kwds):
        if path is None: url = "sqlite+aiosqlite://"
        else: url = "sqlite+aiosqlite:///" + path.as_posix()
        # make dir if parent not exist
        if path: path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(url, **kwds)
        return cls(engine)

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def __aenter__(self):
        return self.engine

    async def __aexit__(self, *exc):
        await self.engine.dispose()


class DefaultStorageHook(StorageEvent):
    # sess: sessionmaker[AsyncSession]

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sess = sessionmaker(self.engine, class_=AsyncSession)

    async def create(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(FeedOrm.metadata.create_all)

    async def SaveFeed(self, feed: BaseFeed, msgs_id: list[int] = None, flush: bool = True):
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
                    FeedOrm.set_by(prev, feed, msgs_id)
                else:
                    # not exist: add
                    sess.add(FeedOrm.from_base(feed, msgs_id))
            if flush: await sess.commit()

    async def exists(self, feed: Union[BaseFeed, FeedRep]) -> bool:
        """check if a feed exists in this database.

        :param feed: feed to check
        :return: whether exists
        """
        return await self.get_orm(
            FeedOrm.uin == feed.uin, FeedOrm.abstime == feed.abstime
        ) is not None

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
        mids = orm.mids
        assert mids is None or isinstance(mids, list)
        return BaseFeed.from_orm(orm), mids

    async def clean(self, seconds: float, timeout: float = None, flush: bool = True):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        :param timeout: timeout as that in :external:meth:`asyncio.wait`, defaults to None
        :param flush: commit at once, defaults to True
        :return: done, pending set as that in :external:meth:`asyncio.wait`
        """
        from time import time
        if seconds <= 0: seconds += time()
        async with self.sess() as sess:
            async with sess.begin():
                result = await sess.execute(select(FeedOrm).where(FeedOrm.abstime < seconds))
                tasks = [asyncio.create_task(sess.delete(i)) for i in result.scalars()]
                r = await asyncio.wait(tasks, timeout=timeout)
            if flush: await sess.commit()
            return r

    async def get_message_id(self, feed: BaseFeed) -> Optional[list[int]]:
        r = await self.get(FeedOrm.uin == feed.uin, FeedOrm.abstime == feed.abstime)
        return r and r[1]

    async def update_message_id(self, feed: BaseFeed, mids: list[int], flush: bool = True):
        async with self.sess() as sess:
            stmt = select(FeedOrm)
            stmt = stmt.where(FeedOrm.uin == feed.uin, FeedOrm.abstime == feed.abstime)
            result = await sess.execute(stmt)
            orm = result.scalar()
            if orm is None: return
            orm.mids = mids
            if flush: await sess.commit()

    def add_clean_task(self, keepdays: int):
        async def clean_sleep():
            while True:
                try:
                    await self.clean(-keepdays * 86400)
                    await asyncio.sleep(86400)
                except asyncio.CancelledError:
                    return

        self.cl = asyncio.create_task(clean_sleep())
        return self.cl
