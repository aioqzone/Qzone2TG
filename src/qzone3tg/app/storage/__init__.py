import asyncio
from pathlib import Path
from time import time
from typing import cast

from aioqzone.type.resp import FeedRep
from aioqzone_feed.type import BaseFeed
from qzemoji.base import AsyncSessionProvider
from sqlalchemy.engine.result import Result
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from ...bot.queue import QueueEvent
from .orm import FeedOrm, MessageOrm


class StorageEvent(QueueEvent):
    async def Clean(self, seconds: float):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        """
        return

    async def Exists(self, feed: FeedRep) -> bool:
        """check if a feed exists in local storage.

        :param feed: feed to check
        :return: whether exists
        """
        return False

    async def Mid2Feed(self, mid: int) -> BaseFeed | None:
        """query feed from message id.

        :param mid: message id
        :return: corresponding feed if exist, else None.
        """
        return


class StorageMan(AsyncSessionProvider):
    async def create(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(FeedOrm.metadata.create_all)

    async def exists(self, *pred) -> bool:
        """check if a feed exists in this database _AND_ it has a message id.

        :param feed: feed to check
        :return: whether exists and is sent
        """
        r: FeedOrm | None = await self.get_feed_orm(*pred)
        if r is None:
            return False
        mids = await self.get_msg_orms(*MessageOrm.fkey(r))
        return bool(mids)

    async def get_feed_orm(self, *where, sess: AsyncSession | None = None) -> FeedOrm | None:
        """Get a feed orm from ``feed`` table, with given criteria.

        :return: a instance of :class:`.FeedOrm` if exist, else None.
        """
        if sess is None:
            async with self.sess() as newsess:
                return await self.get_feed_orm(*where, sess=newsess)

        stmt = select(FeedOrm)
        if where:
            stmt = stmt.where(*where)
        return (await sess.execute(stmt)).scalar()

    async def get_msg_orms(
        self, *where, sess: AsyncSession | None = None
    ) -> list[MessageOrm] | None:
        """Get all satisfying orms from ``message`` table, with given criteria.

        :return: list of :class:`.MessageOrm`s if exist, else None.
        """
        if sess is None:
            async with self.sess() as newsess:
                return await self.get_msg_orms(*where, sess=newsess)

        stmt = select(MessageOrm)
        if where:
            stmt = stmt.where(*where)
        r: Result = await sess.execute(stmt)
        return r.scalars().all() or None

    async def get(self, *pred) -> tuple[BaseFeed, list[int] | None] | None:
        """Get a feed and its message ids from database, with given criteria.
        If multiple records satisfy the criteria, returns the first.

        :return: :external:class:`aioqzone_feed.type.BaseFeed` and message ids, optional
        """
        if (orm := await self.get_feed_orm(*pred)) is None:
            return

        orms = await self.get_msg_orms(*MessageOrm.fkey(orm))
        if orms is None:
            mids = None
        else:
            mids = [cast(int, i.mid) for i in orms]
        return BaseFeed.from_orm(orm), mids

    async def clean(self, seconds: float):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        :return: pending set is empty
        """

        if seconds <= 0:
            seconds += time()
        async with self.sess() as sess:
            sess: AsyncSession
            async with sess.begin():
                result: Result = await sess.execute(
                    select(FeedOrm).where(FeedOrm.abstime < seconds)
                )
                taskm, taskf = [], []
                for mo in result.scalars().all():
                    r: Result = await sess.execute(select(MessageOrm).where(*MessageOrm.fkey(mo)))
                    taskm.extend(asyncio.create_task(sess.delete(i)) for i in r.scalars())
                    taskf.append(asyncio.create_task(sess.delete(mo)))

                if taskm:
                    await asyncio.wait(taskm)
                if taskf:
                    await asyncio.wait(taskf)

                await sess.commit()


class DefaultStorageHook(StorageEvent):
    def __init__(self, man: StorageMan) -> None:
        super().__init__()
        self.man = man

    @property
    def sess(self):
        return self.man.sess

    async def SaveFeed(self, feed: BaseFeed, mids: list[int] | None = None):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param mids: message id list, defaults to None
        """

        async def update_feed(feed, sess: AsyncSession):
            prev = await self.man.get_feed_orm(*FeedOrm.primkey(feed), sess=sess)
            if prev:
                # if exist: update
                FeedOrm.set_by(prev, feed)
            else:
                # not exist: add
                sess.add(FeedOrm.from_base(feed))

        async with self.sess() as sess:
            sess: AsyncSession
            async with sess.begin():
                tasks = [
                    self.UpdateMid(feed, mids, sess=sess, flush=False),
                    update_feed(feed, sess=sess),
                ]
                await asyncio.wait([asyncio.create_task(i) for i in tasks])
                await sess.commit()

    async def GetMid(self, feed: BaseFeed) -> list[int] | None:
        r = await self.man.get_msg_orms(*MessageOrm.fkey(feed))
        if r is None:
            return r
        return [cast(int, i.mid) for i in r]

    async def UpdateMid(
        self,
        feed: BaseFeed,
        mids: list[int] | None,
        sess: AsyncSession | None = None,
        flush: bool = True,
    ):
        if sess is None:
            async with self.sess() as newsess:
                await self.UpdateMid(feed, mids, sess=newsess, flush=flush)
                return

        if flush:
            async with sess.begin():
                await self.UpdateMid(feed, mids, sess=sess, flush=False)
                await sess.commit()
                return

        # query existing mids
        stmt = select(MessageOrm)
        stmt = stmt.where(*MessageOrm.fkey(feed))
        result: Result = await sess.execute(stmt)

        # delete existing mids
        tasks = [asyncio.create_task(sess.delete(i)) for i in result.scalars()]
        if tasks:
            await asyncio.wait(tasks)

        if mids is None:
            return
        for mid in mids:
            sess.add(MessageOrm(uin=feed.uin, abstime=feed.abstime, mid=mid))

    async def Mid2Feed(self, mid: int) -> BaseFeed | None:
        mo = await self.man.get_msg_orms(MessageOrm.mid == mid)
        if not mo:
            return
        orm = await self.man.get_feed_orm(
            FeedOrm.uin == mo[0].uin, FeedOrm.abstime == mo[0].abstime
        )
        if orm is None:
            return
        return BaseFeed.from_orm(orm)

    async def Exists(self, feed: FeedRep) -> bool:
        return await self.man.exists(*FeedOrm.primkey(cast(BaseFeed, feed)))

    async def Clean(self, seconds: float):
        return await self.man.clean(seconds)
