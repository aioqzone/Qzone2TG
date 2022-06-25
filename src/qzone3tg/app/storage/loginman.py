from aioqzone.api.loginman import MixedLoginMan, QrStrategy
from qqqr.utils.net import ClientAdapter
from qzemoji.base import AsyncSessionProvider
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.future import select

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

    async def table_exists(self):
        def sync(conn):
            exist = inspect(conn).has_table(CookieOrm.__tablename__)
            if not exist:
                CookieOrm.metadata.create_all(conn)
            return exist

        async with self.engine.begin() as conn:
            return await conn.run_sync(sync)

    async def load_cached_cookie(self):
        async with self.sess() as sess:
            stmt = select(CookieOrm).where(CookieOrm.uin == self.uin)
            result = await sess.execute(stmt)
        if (prev := result.scalar()) is None:
            return
        self._cookie = prev.cookie
        self.sess.cookie_jar.update_cookies(self._cookie)

    async def _new_cookie(self) -> dict[str, str]:
        r = await super()._new_cookie()
        async with self.sess() as sess:
            async with sess.begin():
                result = await sess.execute(select(CookieOrm).where(CookieOrm.uin == self.uin))
                if prev := result.scalar():
                    # if exist: update
                    prev.cookie = r
                else:
                    # not exist: add
                    sess.add(CookieOrm(uin=self.uin, cookie=r))
            await sess.commit()
        return r
