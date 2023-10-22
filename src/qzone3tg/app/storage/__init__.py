import asyncio
from time import time
from typing import Sequence

from aioqzone_feed.type import BaseFeed
from qzemoji.base import AsyncSessionProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .orm import FeedOrm, MessageOrm


class StorageMan(AsyncSessionProvider):
    async def create(self):
        await self._create(FeedOrm)

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

        :return: an instance of :class:`.FeedOrm` if exist, else None.
        """
        if sess is None:
            async with self.sess() as newsess:
                return await self.get_feed_orm(*where, sess=newsess)

        stmt = select(FeedOrm)
        if where:
            stmt = stmt.where(*where)
        return await sess.scalar(stmt)

    async def get_msg_orms(self, *where, sess: AsyncSession | None = None) -> Sequence[MessageOrm]:
        """Get all satisfying orms from ``message`` table, with given criteria.

        :return: list of :class:`.MessageOrm`s if exist, else None.
        """
        if sess is None:
            async with self.sess() as newsess:
                return await self.get_msg_orms(*where, sess=newsess)

        stmt = select(MessageOrm)
        if where:
            stmt = stmt.where(*where)
        r = await sess.scalars(stmt)
        return r.all()

    async def get(self, *pred) -> tuple[BaseFeed, list[int]] | None:
        """Get a feed and its message ids from database, with given criteria.
        If multiple records satisfy the criteria, returns the first.

        :return: :external:class:`aioqzone_feed.type.BaseFeed` and message ids, optional
        """
        if (orm := await self.get_feed_orm(*pred)) is None:
            return

        orms = await self.get_msg_orms(*MessageOrm.fkey(orm))
        mids = [i.mid for i in orms]
        return (
            BaseFeed(
                **orm.dict(),  # type: ignore
            ),
            mids,
        )

    async def clean(self, seconds: float):
        """clean feeds out of date, based on `abstime`.

        :param seconds: Timestamp in second, clean the feeds before this time. Means back from now if the value < 0.
        :return: pending set is empty
        """

        if seconds <= 0:
            seconds += time()
        async with self.sess() as sess:
            async with sess.begin():
                result = await sess.scalars(select(FeedOrm).where(FeedOrm.abstime < seconds))
                taskm, taskf = [], []
                for mo in result:
                    r = await sess.scalars(select(MessageOrm).where(*MessageOrm.fkey(mo)))
                    taskm.extend(asyncio.create_task(sess.delete(i)) for i in r)
                    taskf.append(asyncio.create_task(sess.delete(mo)))

                if taskm:
                    await asyncio.wait(taskm)
                if taskf:
                    await asyncio.wait(taskf)


class StorageMixin:
    store: StorageMan

    def __init__(self, *args, **kwds) -> None:
        super().__init__(*args, **kwds)

    @property
    def sess_maker(self):
        return self.store.sess

    async def _update_message_ids(
        self,
        feed: BaseFeed,
        mids: list[int] | None,
        sess: AsyncSession | None = None,
        flush: bool = True,
    ):
        if sess is None:
            async with self.sess_maker() as newsess:
                await self._update_message_ids(feed, mids, sess=newsess, flush=flush)
            return

        if flush:
            await self._update_message_ids(feed, mids, sess=sess, flush=False)
            await sess.commit()
            return

        # query existing mids
        stmt = select(MessageOrm)
        stmt = stmt.where(*MessageOrm.fkey(feed))
        result = await sess.scalars(stmt)

        # delete existing mids
        tasks = [asyncio.create_task(sess.delete(i)) for i in result]
        if tasks:
            await asyncio.wait(tasks)

        if mids is None:
            return
        for mid in mids:
            sess.add(MessageOrm(uin=feed.uin, abstime=feed.abstime, mid=mid))

    async def SaveFeed(self, feed: BaseFeed, mids: list[int] | None = None):
        """Add/Update an record by the given feed and messages id.

        :param feed: feed
        :param mids: message id list, defaults to None
        """

        async def _update_feed(feed, sess: AsyncSession):
            prev = await self.store.get_feed_orm(*FeedOrm.primkey(feed), sess=sess)
            if prev:
                # if exist: update
                FeedOrm.set_by(prev, feed)
            else:
                # not exist: add
                sess.add(FeedOrm.from_base(feed))

        async with self.sess_maker() as sess:
            async with sess.begin():
                # BUG: asyncio.wait/gather raises error at the end of a transaction
                await self._update_message_ids(feed, mids, sess=sess, flush=False)
                await _update_feed(feed, sess=sess)

    async def Mid2Feed(self, mid: int) -> BaseFeed | None:
        mo = await self.store.get_msg_orms(MessageOrm.mid == mid)
        if not mo:
            return
        orm = await self.store.get_feed_orm(
            FeedOrm.uin == mo[0].uin, FeedOrm.abstime == mo[0].abstime
        )
        if orm is None:
            return
        return BaseFeed(**orm.dict())  # type: ignore
