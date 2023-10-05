from typing import cast

from sqlalchemy import Connection, Table, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .orm import CookieOrm

__all__ = ["table_exists", "load_cached_cookie", "save_cookie"]


async def table_exists(engine: AsyncEngine) -> bool:
    def ensure_table(conn: Connection):
        """
        .. versionchanged:: 0.6.0.dev2

            Check if the ``cookie`` table has a ``p_skey`` and ``pt4_token`` column.
            If not, reconstruct the schema.
        """
        nsp = inspect(conn)
        exist = nsp.has_table(CookieOrm.__tablename__)
        if not exist:
            CookieOrm.metadata.create_all(conn)
            return False

        cols = nsp.get_columns("cookie")
        names = set(col["name"] for col in cols)
        if all(k in names for k in ("p_skey", "pt4_token")):
            return True

        # drop table
        cast(Table, CookieOrm.__table__).drop(conn)
        CookieOrm.metadata.create_all(conn)
        return True

    async with engine.begin() as conn:
        return await conn.run_sync(ensure_table)


async def load_cached_cookie(uin: int, engine: AsyncEngine) -> dict[str, str] | None:
    async with async_sessionmaker(engine)() as sess:
        stmt = select(CookieOrm).where(CookieOrm.uin == uin)
        prev = await sess.scalar(stmt)

    if prev is None:
        return

    return dict(
        p_uin="o" + str(uin).zfill(10),
        p_skey=prev.p_skey,
        pt4_token=prev.pt4_token,
    )


async def save_cookie(r: dict[str, str], uin: int, sess: AsyncSession) -> None:
    if not all(k in r for k in ("p_skey", "pt4_token")):
        return

    async with sess.begin():
        prev = await sess.scalar(select(CookieOrm).where(CookieOrm.uin == uin))
        if prev:
            # if exist: update
            prev.p_skey = r["p_skey"]
            prev.pt4_token = r["pt4_token"]
        else:
            # not exist: add
            sess.add(CookieOrm(uin=uin, p_skey=r["p_skey"], pt4_token=r["pt4_token"]))
