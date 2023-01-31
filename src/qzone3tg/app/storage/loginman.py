from typing import cast

from aioqzone.api.loginman import MixedLoginMan, QrStrategy
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncSessionProvider
from sqlalchemy import Connection, Table, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine

from .orm import CookieOrm


class LoginMan(MixedLoginMan, AsyncSessionProvider):
    """Login manager with cookie caching.

    .. versionadded:: 0.1.3
    """

    def __init__(
        self,
        client: ClientAdapter,
        engine: AsyncEngine,
        uin: int,
        strategy: QrStrategy,
        pwd: str | None = None,
        refresh_time: int = 6,
    ) -> None:
        MixedLoginMan.__init__(self, client, uin, strategy, pwd, refresh_time)
        AsyncSessionProvider.__init__(self, engine)
        self.client = client

    async def table_exists(self):
        def ensure_table(conn: Connection):
            """
            .. versionchanged:: 0.6.0.dev2

                check if the ``cookie`` table has a ``p_skey`` column. If not, replace the schema.
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

        async with self.engine.begin() as conn:
            return await conn.run_sync(ensure_table)

    async def load_cached_cookie(self):
        async with self.sess() as sess:
            stmt = select(CookieOrm).where(CookieOrm.uin == self.uin)
            prev = await sess.scalar(stmt)
        if prev is None:
            return
        self._cookie = dict(
            p_uin="o" + str(self.uin).zfill(10),
            p_skey=prev.p_skey,
            pt4_token=prev.pt4_token,
        )
        self.client.client.cookies.update(self._cookie)

    async def _new_cookie(self) -> dict[str, str]:
        r = await super()._new_cookie()
        if not all(k in r for k in ("p_skey", "pt4_token")):
            return r

        async with self.sess() as sess:
            async with sess.begin():
                prev = await sess.scalar(select(CookieOrm).where(CookieOrm.uin == self.uin))
                if prev:
                    # if exist: update
                    prev.p_skey = r["p_skey"]
                    prev.pt4_token = r["pt4_token"]
                else:
                    # not exist: add
                    sess.add(CookieOrm(uin=self.uin, p_skey=r["p_skey"], pt4_token=r["pt4_token"]))
        return r
