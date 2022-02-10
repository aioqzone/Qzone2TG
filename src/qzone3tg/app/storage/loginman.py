from aiohttp import ClientSession
from aioqzone.api.loginman import MixedLoginMan
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from .orm import CookieOrm


class LoginMan(MixedLoginMan):
    """Login manager with cookie caching.

    .. versionadded:: 0.1.3
    """
    def __init__(
        self,
        sess: ClientSession,
        engine: AsyncEngine,
        uin: int,
        strategy: str,
        pwd: str = None,
        refresh_time: int = 6
    ) -> None:
        super().__init__(sess, uin, strategy, pwd, refresh_time)
        self.engine = engine
        self.sessmaker = sessionmaker(self.engine, class_=AsyncSession)

    async def load_cached_cookie(self):
        async with self.sessmaker() as sess:
            stmt = select(CookieOrm).where(CookieOrm.uin == self.uin)
            result = await sess.execute(stmt)
        if (prev := result.scalar()) is None: return
        self._cookie = prev.cookie
        self.sess.cookie_jar.update_cookies(self._cookie)

    async def _new_cookie(self) -> dict[str, str]:
        r = await super()._new_cookie()
        async with self.sessmaker() as sess:
            async with sess.begin():
                result = await sess.execute(select(CookieOrm).where(CookieOrm.uin == self.uin))
                if (prev := result.scalar()):
                    # if exist: update
                    prev.cookie = r
                else:
                    # not exist: add
                    sess.add(CookieOrm(uin=self.uin, cookie=r))
            await sess.commit()
        return r
