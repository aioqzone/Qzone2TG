import logging
import typing as t
from http.cookies import SimpleCookie

from aioqzone.api import (
    ConstLoginMan,
    QrLoginConfig,
    QrLoginManager,
    UpLoginConfig,
    UpLoginManager,
)
from qzemoji.base import AsyncSessionProvider
from sqlalchemy import Connection, Table, inspect, select

from .orm import CookieOrm

__all__ = ["LoginManager"]

log = logging.getLogger(__name__)

if t.TYPE_CHECKING:
    from aiohttp import ClientSession
    from sqlalchemy.ext.asyncio import AsyncEngine

ALL_FIELDS = "p_skey", "pt4_token", "pt_guid_sig", "ptcz"


class LoginManager(AsyncSessionProvider, ConstLoginMan):
    """The login manager used in app. It combines qr & up login manager,
    and has built-in cookie persistance.
    """

    def __init__(
        self,
        client: "ClientSession",
        engine: "AsyncEngine",
        qr_config: QrLoginConfig,
        up_config: UpLoginConfig,
    ) -> None:
        super().__init__(engine=engine, uin=up_config.uin)
        self.qr = QrLoginManager(client, qr_config)
        self.up = UpLoginManager(client, up_config)

        self.register_hooks()

    def register_hooks(self):
        @self.up.login_success.add_impl
        async def up_login_success(uin: int):
            self.cookie.update(self.up.cookie)
            log.debug(f"update cookie from uplogin: {self.cookie}")
            await self.save_cookie(self.up.cookie)

        @self.qr.login_success.add_impl
        async def qr_login_success(uin: int):
            self.cookie.update(self.qr.cookie)
            log.debug(f"update cookie from qrlogin: {self.cookie}")
            await self.save_cookie(self.qr.cookie)

    async def table_exists(self) -> bool:
        def ensure_table(conn: Connection):
            """
            .. versionchanged:: 0.6.0.dev2

                Check if the ``cookie`` table has :obj:`ALL_FIELDS`.
                If not, reconstruct the schema.
            """
            nsp = inspect(conn)
            exist = nsp.has_table(CookieOrm.__tablename__)
            if not exist:
                CookieOrm.metadata.create_all(conn)
                return False

            cols = nsp.get_columns("cookie")
            names = set(col["name"] for col in cols)
            if all(k in names for k in ALL_FIELDS):
                return True

            # drop table
            t.cast(Table, CookieOrm.__table__).drop(conn)
            CookieOrm.metadata.create_all(conn)
            return True

        async with self.engine.begin() as conn:
            return await conn.run_sync(ensure_table)

    async def load_cached_cookie(self) -> bool:
        async with self.sess() as sess:
            stmt = select(CookieOrm).where(CookieOrm.uin == self.uin)
            prev = await sess.scalar(stmt)

        if prev is None:
            return False

        cookies = dict(
            p_uin="o" + str(self.uin).zfill(10),
            p_skey=prev.p_skey,
            pt4_token=prev.pt4_token,
            pt_guid_sig=prev.pt_guid_sig,
            ptcz=prev.ptcz,
        )
        self.cookie.update(cookies)
        log.debug(f"update cookie from storage: {self.cookie}")

        cookies = SimpleCookie(cookies)
        domains = dict(
            p_uin="qzone.qq.com",
            p_skey="qzone.qq.com",
            pt4_token="qq.com",
            pt_guid_sig="ptlogin2.qq.com",
            ptcz="qq.com",
        )
        for k, v in domains.items():
            cookies[k].update({"path": "/", "domain": v})
        self.up.client.cookie_jar.update_cookies(cookies)

        return True

    async def save_cookie(self, r: dict[str, str]) -> None:
        if not all(k in r for k in ALL_FIELDS):
            return

        async with self.sess() as sess, sess.begin():
            prev = await sess.scalar(select(CookieOrm).where(CookieOrm.uin == self.uin))
            if prev:
                # if exist: update
                prev.p_skey = r["p_skey"]
                prev.pt4_token = r["pt4_token"]
                prev.pt_guid_sig = r["pt_guid_sig"]
                prev.ptcz = r["ptcz"]
            else:
                # not exist: add
                sess.add(
                    CookieOrm(
                        uin=self.uin,
                        p_skey=r["p_skey"],
                        pt4_token=r["pt4_token"],
                        pt_guid_sig=r["pt_guid_sig"],
                        ptcz=r["ptcz"],
                    )
                )

            await sess.commit()
