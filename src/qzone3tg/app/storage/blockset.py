from qzemoji.base import AsyncSessionProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .orm import BlockOrm


class BlockSet(AsyncSessionProvider):
    async def create(self):
        await self._create(BlockOrm)

    async def contains(self, uin: int, sess: AsyncSession | None = None):
        if sess is None:
            async with self.sess() as sess:
                return await self.contains(uin, sess=sess)

        stmt = select(BlockOrm).where(BlockOrm.uin == uin)
        return (await sess.scalar(stmt)) is not None

    async def add(self, uin: int, sess: AsyncSession | None = None, flush=True):
        if sess is None:
            async with self.sess() as sess:
                return await self.add(uin, sess=sess, flush=flush)

        sess.add(BlockOrm(uin=uin))

        if flush:
            await sess.commit()

    async def delete(self, uin: int, sess: AsyncSession | None = None, flush=True):
        if sess is None:
            async with self.sess() as sess:
                return await self.delete(uin, sess=sess, flush=flush)

        stmt = select(BlockOrm).where(BlockOrm.uin == uin)
        if r := await sess.scalar(stmt):
            await sess.delete(r)
            if flush:
                await sess.commit()

    async def all(self, sess: AsyncSession | None = None) -> list[int]:
        if sess is None:
            async with self.sess() as sess:
                return await self.all(sess=sess)

        r = await sess.scalars(select(BlockOrm))
        return [i.uin for i in r]
