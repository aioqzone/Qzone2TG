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
        self.sess = sessionmaker(self.engine, class_=AsyncSession)

    async def _new_cookie(self) -> dict[str, str]:
        r = await super()._new_cookie()
        async with self.sess() as sess:
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
