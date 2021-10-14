import logging
import time
from random import random
from typing import Callable, Dict, Optional

import requests
from middleware.storage import TokenTable
from middleware.uihook import NullUI
from requests.exceptions import ConnectionError, HTTPError
from tencentlogin.base import UA as DefaultUA
from tencentlogin.constants import QzoneAppid, QzoneProxy
from tencentlogin.encrypt import gtk
from tencentlogin.exception import TencentLoginError
from tencentlogin.qr import QRLogin
from tencentlogin.up import UPLogin, User
from utils.decorator import Retry, cached, noexcept

from .common import UPDATE_FEED_URL
from .exceptions import LoginError, QzoneError, UserBreak

logger = logging.getLogger(__name__)

__all__ = ['HBMgr']


class _LoginHelper:
    hook = NullUI()

    def __init__(
        self, uin: int, *, pwd: str = None, qr_strategy: str = 'prefer'
    ) -> None:
        self.uin = uin
        self.pwd = pwd
        self.qr_strategy = qr_strategy
        if qr_strategy != 'force':
            assert self.pwd
            self._up = UPLogin(QzoneAppid, QzoneProxy, User(self.uin, self.pwd))
        if qr_strategy != 'forbid':
            self._qr = QRLogin(QzoneAppid, QzoneProxy)

    def register_ui_hook(self, hook: NullUI):
        self.hook = hook
        self.hook.register_resend_callback(self._qr.show)

    def _upLogin(self) -> Optional[dict]:
        """login use uin and pwd

        Returns:
            Optional[dict]: cookie dict if success, else None
        """
        try:
            return self._up.login(self._up.check(), all_cookie=True)
        except TencentLoginError as e:
            logger.warning(str(e))

    def _qrLogin(self, refresh_time=6) -> Optional[dict]:
        """Login with QR. BLOCK until user interact or timeout.

        Raises:
            UserBreak: if user break the login procedure.

        Returns:
            Optional[dict]: cookie dict if success, else None
        """
        r = [None]
        sched = self._qr.loop(refresh_time=refresh_time, all_cookie=True)(  # yapf: disable
            refresh_callback=lambda b: sendmethod()(b),
            return_callback=lambda b: r.__setitem__(0, b),
        )
        sendmethod = lambda: self.hook.QrExpired if sched.cnt else self.hook.QrFetched
        self.hook.register_cancel_callback(lambda: sched.stop(exception=True))
        try:
            sched.start()
            r = r[0]
            if r: self.hook.QrScanSucceessed()
            else: self.hook.QrFailed()
            return r
        except TimeoutError:
            self.hook.QrFailed()
            return
        except KeyboardInterrupt:
            raise UserBreak

    def login(self) -> Dict[str, str]:
        """login and return cookie according to qr_strategy

        Returns:
            Optional[dict]: cookie dict if success, else None

        Raises:
            UserBreak
        """
        for f in {
                'force': (self._qrLogin, ),
                'prefer': (self._qrLogin, self._upLogin),
                'allow': (self._upLogin, self._qrLogin),
                'forbid': (self._upLogin, ),
        }[self.qr_strategy]:
            if (r := f()): return r

        if self.qr_strategy == 'forbid':
            raise LoginError("您可能被限制账密登陆, 或自动跳过验证失败. 扫码登陆仍然可行.", 'forbid')
        else:
            raise LoginError("您可能被限制登陆, 或自动跳过验证失败.", self.qr_strategy)


class _HTTPHelper:
    def __init__(self, uin: int, UA: str = DefaultUA) -> None:
        self.header = {
            'User-Agent': UA,
            "Referer": f"https://user.qzone.qq.com/{uin}",
            "dnt": "1"
        }
        self.session = requests.Session()

    class _403Handler:
        def __init__(self, handler: Callable) -> None:
            self._excc = {HTTPError: handler}

        def register(self, excr=None):
            return Retry(self._excc, excr=excr, with_self=True)

    @_403Handler
    def retry_403(self, e: HTTPError, i):
        if e.response.status_code != 403: raise e
        if i >= 1: raise e

    @noexcept({ConnectionError: lambda _: logger.error('ConnectionError when post.')})
    @retry_403.register()
    def post(self, *args, **kwargs):
        r = self.session.post(*args, **kwargs, headers=self.header)
        r.raise_for_status()
        return r

    @noexcept({ConnectionError: lambda _: logger.error('ConnectionError when get.')})
    @retry_403.register()
    def get(self, *args, **kwargs):
        r = self.session.get(*args, **kwargs, headers=self.header)
        r.raise_for_status()
        return r


class HBMgr(_LoginHelper, _HTTPHelper):
    lastLG: float = None
    lastHB: float = None

    def __init__(
        self,
        token_tbl: TokenTable,
        qq: int,
        *,
        password: str = None,
        qr_strategy: str = 'prefer',
        UA=None,
    ) -> None:
        qq = int(qq)
        _LoginHelper.__init__(self, qq, pwd=password, qr_strategy=qr_strategy)
        _HTTPHelper.__init__(self, qq, UA=UA)
        self.db = token_tbl
        self._gtk = None

    @cached
    def gtk(self):
        return self.updateStatus()

    def updateStatus(self, force_login=False) -> int:
        """update cookie, gtk

        Args:
            `force_login` (bool, optional): force to login. Defaults to False.

        Returns:
            int: gtk

        Raises:
            `UserBreak`: SIGINT is sent or `UserBreak` sent by user
            `LoginError`: Cannot get cookie under current strategy
        """
        if self.uin in self.db:
            if not force_login: cookie = self.db[self.uin]
        else:
            force_login = True

        if force_login:
            logger.info("重新登陆.")
            cookie = self.login()

            if "p_skey" not in cookie:
                raise LoginError("或许可以重新登陆.", self.qr_strategy)

            logger.info('取得cookie')
            self.lastLG = time.time()
            self.hook.loginSuccessed()

            self.db[self.uin] = cookie
        else:
            logger.info("使用缓存cookie")

        self.session.cookies.update(cookie)
        return gtk(cookie["p_skey"])

    class _LoginExpireHandler:
        def __init__(self, handler: Callable) -> None:
            self._excc = {QzoneError: handler}

        def register(self, excr=None):
            return Retry(self._excc, 12, excr=excr, with_self=True)

    @_LoginExpireHandler
    def login_if_expire(self, e: QzoneError, i):
        if e.code == -10001:
            if i >= 11: raise TimeoutError('Qzone interface busy')
            logger.info(e.msg)
            time.sleep(i + 1)
            return

        if e.code not in [-3000, -4002]: raise e
        if self.uin in self.db:
            del self.db[self.uin]

        if i >= 1: raise e
        logger.info("cookie已过期, 即将重新登陆.")
        self.updateStatus(force_login=True)

    @login_if_expire.register(0)
    def checkUpdate(self, parse_callback: Callable[[str], int] = None) -> Optional[int]:
        query = {'uin': self.uin, 'rd': random(), 'g_tk': self.gtk}
        r = self.get(UPDATE_FEED_URL, params=query)
        if r is None: return 0

        logger.debug('heartbeat OK')
        self.lastHB = time.time()

        return parse_callback and parse_callback(r.text)

    def status(self):
        return {
            'last_heartbeat': self.lastHB,
            'last_login': self.lastLG,
        }
