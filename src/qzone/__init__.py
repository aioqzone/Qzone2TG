"""
qzone: 
    Fetch feeds from qzone, Along with qzone login and cookie management.
    
    credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py
"""

import json
import logging
import re
import time
from random import random
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote, unquote

import requests
from jssupport.jsjson import json_loads
from middleware.storage import TokenTable
from middleware.uihook import NullUI
from requests.exceptions import ConnectionError, HTTPError
from tencentlogin.constants import QzoneAppid, QzoneProxy
from tencentlogin.encrypt import gtk
from tencentlogin.exception import TencentLoginError
from tencentlogin.qr import QRLogin
from tencentlogin.up import UPLogin, User
from utils.decorator import Retry, noexcept

from .common import *
from .exceptions import LoginError, QzoneError, UserBreak

logger = logging.getLogger(__name__)

PROXY_DOMAIN = "https://user.qzone.qq.com/proxy/domain"
COMPLETE_FEED_URL = PROXY_DOMAIN + "/taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
DO_LIKE_URL = PROXY_DOMAIN + "/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
GET_PAGE_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
UPDATE_FEED_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi"

BLOCK_LIST = [
    20050606,      # Qzone Official
]

RE_CALLBACK = re.compile(r"callback\((\{.*\})", re.S | re.I)


class LoginHelper:
    ui = NullUI()

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

    def register_ui_hook(self, ui: NullUI):
        self.ui = ui
        self.ui.register_resend_callback(self._qr.show)

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
        sendmethod = lambda: self.ui.QrExpired if sched.cnt else self.ui.QrFetched
        self.ui.register_cancel_callback(lambda: sched.stop(exception=True))
        try:
            sched.start()
            r = r[0]
            if r: self.ui.QrScanSucceessed()
            else: self.ui.QrFailed()
            return r
        except TimeoutError:
            self.ui.QrFailed()
            return
        except KeyboardInterrupt:
            raise UserBreak

    def login(self) -> Optional[dict]:
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
        return


class _DecHelper:
    class CallBacks:
        @staticmethod
        def onLoginExpire(self, e: QzoneError, i):
            if e.code == -10001:
                if i >= 11: raise TimeoutError('Network is always busy!')
                logger.info(e.msg)
                time.sleep(5)
                return

            if e.code not in [-3000, -4002]: raise e
            if self.uin in self.db:
                del self.db[self.uin]

            if i >= 1: raise e
            logger.info("cookie已过期, 即将重新登陆.")
            QzoneScraper.updateStatus(self, force_login=True)

        @staticmethod
        def onHTTPError(e: HTTPError, i):
            if e.response.status_code != 403: raise e
            if i >= 1: raise e

    login_if_expire = Retry(
        {QzoneError: CallBacks.onLoginExpire},
        times=12,
        with_self=True,
    )

    retry_403 = Retry({HTTPError: CallBacks.onHTTPError})


class HTTPHelper:
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36 Edg/94.0.992.31"

    def __init__(self, uin, UA=None) -> None:
        self.header = {
            'User-Agent': UA or self.UA,
            "Referer": f"https://user.qzone.qq.com/{uin}",
            "dnt": "1"
        }
        self.session = requests.Session()

    @noexcept({ConnectionError: lambda e: logger.error('ConnectionError when post.')})
    @_DecHelper.retry_403
    def post(self, *args, **kwargs):
        r = self.session.post(*args, **kwargs, headers=self.header)
        r.raise_for_status()
        return r

    @noexcept({ConnectionError: lambda e: logger.error('ConnectionError when get.')})
    @_DecHelper.retry_403
    def get(self, *args, **kwargs):
        r = self.session.get(*args, **kwargs, headers=self.header)
        r.raise_for_status()
        return r


class QzoneScraper(LoginHelper, HTTPHelper):
    gtk: int = None

    def __init__(
        self,
        token_tbl: TokenTable,
        qq: Union[str, int],
        *,
        password: str = None,
        qr_strategy='prefer',
        UA=None,
    ):
        qq = int(qq)
        LoginHelper.__init__(self, qq, pwd=password, qr_strategy=qr_strategy)
        HTTPHelper.__init__(self, qq, UA)
        self.db = token_tbl
        self.extern = {1: "undefined"}

    @staticmethod
    def parseExternParam(unquoted: str) -> dict:
        if unquoted == "undefined": return {}
        dic = {}
        for i in unquoted.split('&'):
            s = i.split('=')
            dic[s[0]] = s[1] if len(s) > 1 else None
        return dic

    def getCompleteFeed(self, feedData: dict) -> Optional[str]:
        if not feedData: return

        body = {
            "uin": feedData["uin"],
            "tid": feedData["tid"],
            "feedsType": feedData["feedstype"],
            "qzreferrer": f"https://user.qzone.qq.com/{self.uin}",
        }
        body.update(Arg4CompleteFeed)

        r = self.post(COMPLETE_FEED_URL, params={'g_tk': self.gtk}, data=body)
        if r is None: return

        r = RE_CALLBACK.search(r.text).group(1)
        r = json.loads(r)
        if r["err"] == 0: return r["newFeedXML"].strip()

    def updateStatus(self, force_login=False):
        """update cookie, gtk

        Args:
            `force_login` (bool, optional): force to login. Defaults to False.

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

            e = None
            if cookie is None:
                if self.qr_strategy == 'forbid':
                    e = LoginError("您可能被限制账密登陆, 或自动跳过验证失败. 扫码登陆仍然可行.", 'forbid')
                else:
                    e = LoginError("您可能被限制登陆, 或自动跳过验证失败.", self.qr_strategy)
            elif "p_skey" not in cookie:
                e = LoginError("或许可以重新登陆.", self.qr_strategy)
            if e:
                self.ui.loginFailed(e.args[0])
                raise e

            logger.info('取得cookie')
            self.ui.loginSuccessed()

            self.db[self.uin] = cookie
        else:
            logger.info("使用缓存cookie")

        self.gtk = gtk(cookie["p_skey"])
        self.session.cookies.update(cookie)

    @_DecHelper.login_if_expire
    def doLike(self, likedata: dict) -> bool:
        """like a post according to likedata

        - login_if_expire

        Args:
            likedata (dict): data contains essential args to like a post

        Raises:
            QzoneError: Error from qzone interface

        Returns:
            bool: if success
        """
        if self.gtk is None: self.updateStatus()
        body = {
            'qzreferrer': f'https://user.qzone.qq.com/{self.uin}',
            'opuin': self.uin,
            'from': 1,
            'active': 0,
            'fupdate': 1,
            'fid': likedata.get('key', None) or likedata.get('fid', None)
        }
        body.update(likedata)
        try:
            r = self.post(DO_LIKE_URL, params={'g_tk': self.gtk}, data=body)
        except HTTPError:
            return False
        if r is None: return False

        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(RE_CALLBACK.search(r).group(1))

        if r["code"] == 0: return True
        else: raise QzoneError(r["code"], r["message"])

    @_DecHelper.login_if_expire
    def fetchPage(
        self,
        pagenum: int,
        count: int = 10,
    ) -> Optional[List[Dict[str, Any]]]:
        """fetch a page of feeds

        - login_if_expire
        
        Args:
            pagenum (int): page #
            count (int, optional): Max feeds num. Defaults to 10.

        Raises:
            `UserBreak`: see `updateStatus`
            `LoginError`: see `updateStatus`
            `QzoneError`: exceptions that are raised by Qzone
            `TimeoutError`: if no respone get 200 in `fetch_times` times.

        Returns:
            `list[dict[str, Any]] | None`, each dict reps a feed.
            None is caused by retry decorator.
        """
        if self.gtk is None: self.updateStatus()

        query = {
            'rd': random(),
            'uin': self.uin,
            'pagenum': pagenum,
            'g_tk': self.gtk,
            'begintime': self.parseExternParam(self.extern[pagenum]
                                               ).get("basetime", "undefined"),
            'count': count,
            'usertime': round(time.time() * 1000),
            'externparam': quote(self.extern[pagenum])
        }
        query.update(Args4GettingFeeds)

        r = self.get(GET_PAGE_URL, params=query)
        if r is None: return []

        r = RE_CALLBACK.search(r.text).group(1)
        r = json_loads(r)
        if r['code'] != 0:
            raise QzoneError(r['code'], r['message'])

        data: dict = r['data']
        self.extern[pagenum + 1] = unquote(data['main']["externparam"])
        feeddict = filter(
            lambda i: not (
                not i or                                    # `undefined` in feed datas or empty feed dict
                i['key'].startswith('advertisement_app') or # ad feed
                int(i['appid']) >= 4096 or                  # not supported (cannot encode)
                int(i['uin']) in BLOCK_LIST                 # in blocklist
            ),
            data['data']
        )
        return list(feeddict)

    @_DecHelper.login_if_expire
    def checkUpdate(self) -> int:
        """return the predict of new feed amount.

        Raises:
            QzoneError: if unkown qzone code returned

        Returns:
            int: super of new feed amount
        """
        if self.gtk is None: self.updateStatus()
        query = {'uin': self.uin, 'rd': random(), 'g_tk': self.gtk}
        r = self.get(UPDATE_FEED_URL, params=query)
        if r is None: return 0
        logger.debug('heartbeat OK')

        r = RE_CALLBACK.search(r.text).group(1)
        r = json_loads(r)
        if r["code"] != 0: raise QzoneError(r['code'], r['message'])

        r = r['data']
        cal_item = 'friendFeeds_new_cnt', 'friendFeeds_newblog_cnt', 'friendFeeds_newphoto_cnt', 'myFeeds_new_cnt'
        return sum(r[i] for i in cal_item)
