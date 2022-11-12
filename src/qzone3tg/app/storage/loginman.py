from aioqzone.api.loginman import MixedLoginMan, QrStrategy
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncSessionProvider
from sqlalchemy import Connection, inspect, select
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
        def sync(conn: Connection):
            exist = inspect(conn).has_table(CookieOrm.__tablename__)
            if not exist:
                CookieOrm.metadata.create_all(conn)
            return exist

        async with self.engine.begin() as conn:
            return await conn.run_sync(sync)

    async def load_cached_cookie(self):
        async with self.sess() as sess:
            stmt = select(CookieOrm).where(CookieOrm.uin == self.uin)
            prev = await sess.scalar(stmt)
        if prev is None:
            return
        self._cookie = dict(p_skey=prev.p_skey)
        self.client.client.cookies.update(self._cookie)

    async def _new_cookie(self) -> dict[str, str]:
        r = await super()._new_cookie()
        if "p_skey" not in r:
            return r

        async with self.sess() as sess:
            async with sess.begin():
                prev = await sess.scalar(select(CookieOrm).where(CookieOrm.uin == self.uin))
                if prev:
                    # if exist: update
                    prev.p_skey = r["p_skey"]
                else:
                    # not exist: add
                    sess.add(CookieOrm(uin=self.uin, p_skey=r["p_skey"]))
            await sess.commit()
        return r
