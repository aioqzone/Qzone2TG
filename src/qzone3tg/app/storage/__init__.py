import asyncio
from pathlib import Path
from typing import cast

from aioqzone.type import FeedRep
from aioqzone_feed.type import BaseFeed
from aioqzone_feed.utils.task import AsyncTimer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from ...bot.queue import QueueEvent
from .orm import FeedOrm


class StorageEvent(QueueEvent):
    async def clean(self, seconds: float):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        """
        return

    async def exists(self, feed: FeedRep) -> bool:
        """check if a feed exists in local storage.

        :param feed: feed to check
        :return: whether exists
        """
        return False


class AsyncEnginew:
    @classmethod
    def sqlite3(cls, path: Path | None, **kwds):
        if path is None:
            url = "sqlite+aiosqlite://"
        else:
            url = "sqlite+aiosqlite:///" + path.as_posix()
        # make dir if parent not exist
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
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
        self._sess = sessionmaker(self.engine, class_=AsyncSession)

    async def create(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(FeedOrm.metadata.create_all)

    @property
    def sess(self):
        self.__ensure_async_mutex()
        return self._sess

    def __ensure_async_mutex(self):
        """A temp fix to self.engine.pool.dispatch.connect._exec_once_mutex blocked"""
        from _thread import LockType

        try:
            if isinstance(self.engine.pool.dispatch.connect._exec_once_mutex, LockType):
                self.engine.pool.dispatch.connect._set_asyncio()
        except AttributeError:
            return

    async def SaveFeed(self, feed: BaseFeed, msgs_id: list[int] | None = None, flush: bool = True):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param mid_ls: messages id list, defaults to None
        :param flush: commit at once, defaults to True
        """
        async with self.sess() as sess:
            async with sess.begin():
                prev = await self.get_orm(*FeedOrm.primkey(feed), sess=sess)
                if prev:
                    # if exist: update
                    FeedOrm.set_by(prev, feed, msgs_id)
                else:
                    # not exist: add
                    sess.add(FeedOrm.from_base(feed, msgs_id))
            if flush:
                await sess.commit()

    async def exists(self, feed: BaseFeed | FeedRep) -> bool:
        """check if a feed exists in this database.

        :param feed: feed to check
        :return: whether exists
        """
        return await self.get_orm(*FeedOrm.primkey(cast(BaseFeed, feed))) is not None

    async def get_orm(self, *where, sess: AsyncSession | None = None) -> FeedOrm | None:
        """Get a feed orm from database, with given criteria.

        :return: :class:`.FeedOrm`
        """
        stmt = select(FeedOrm)
        if where:
            stmt = stmt.where(*where)
        if sess:
            return (await sess.execute(stmt)).scalar()
        async with self.sess() as sess:
            assert sess
            return (await sess.execute(stmt)).scalar()

    async def get(self, *pred) -> tuple[BaseFeed, list[int] | None] | None:
        """Get a feed from database, with given criteria.
        If multiple records satisfy the criteria, returns the first.

        :return: :external:class:`aioqzone_feed.type.BaseFeed` and message ids, optional
        """
        if (orm := await self.get_orm(*pred)) is None:
            return
        mids = orm.mids
        assert mids is None or isinstance(mids, list)
        return BaseFeed.from_orm(orm), mids

    async def clean(self, seconds: float, timeout: float | None = None, flush: bool = True):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        :param timeout: timeout as that in :external:meth:`asyncio.wait`, defaults to None
        :param flush: commit at once, defaults to True
        :return: pending set is empty
        """
        from time import time

        if seconds <= 0:
            seconds += time()
        async with self.sess() as sess:
            async with sess.begin():
                result = await sess.execute(select(FeedOrm).where(FeedOrm.abstime < seconds))
                tasks = [asyncio.create_task(sess.delete(i)) for i in result.scalars()]
                if not tasks:
                    return False
                _, pending = await asyncio.wait(tasks, timeout=timeout)
            if flush:
                await sess.commit()
            return not pending

    async def get_message_id(self, feed: BaseFeed) -> list[int] | None:
        r = await self.get(*FeedOrm.primkey(feed))
        return r and r[1]

    async def update_message_id(self, feed: BaseFeed, mids: list[int], flush: bool = True):
        async with self.sess() as sess:
            orm = await self.get_orm(*FeedOrm.primkey(feed), sess=sess)
            if orm is None:
                return
            orm.mids = mids
            if flush:
                await sess.commit()

    def add_clean_task(self, keepdays: int, interval: float = 86400):
        """
        This function register a timer that calls `self.clean(-keepdays * 86400)`
        every `interval` seconds.

        :param keepdays: Used to determine how many days worth of messages to keep.
        :return: the clean Task
        """

        async def clean():
            await self.clean(-keepdays * 86400)
            return False

        self.cl = AsyncTimer(interval, clean, name="clean")
        self.cl()
        return self.cl
