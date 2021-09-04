"""
qzone: 
    Fetch feeds from qzone, Along with qzone login and cookie management.
    
    credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py
"""

import json
import logging
import re
import time
from typing import Union
from urllib.parse import quote, unquote

import requests
from jssupport.jsjson import json_loads
from requests.exceptions import HTTPError
from tencentlogin import TencentLoginError
from tencentlogin.constants import QzoneAppid, QzoneProxy
from tencentlogin.qr import QRLogin
from tencentlogin.up import UPLogin, User
from middleware.uihook import NullUI
from middleware.storage import TokenTable
from utils.decorator import Retry

from .common import *
from .exceptions import LoginError, QzoneError, UserBreak

logger = logging.getLogger(__name__)

PROXY_DOMAIN = "https://user.qzone.qq.com/proxy/domain"
COMPLETE_FEED_URL = PROXY_DOMAIN + "/taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
DO_LIKE_URL = PROXY_DOMAIN + "/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
GET_PAGE_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
UPDATE_FEED_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi"

RE_CALLBACK = re.compile(r"callback\((\{.*\})", re.S | re.I)


class LoginHelper:
    ui = NullUI()

    def __init__(self, uin: int, *, pwd: str = None, qr_strategy='prefer') -> None:
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

    def _upLogin(self) -> dict:
        try:
            return self._up.login(self._up.check(), all_cookie=True)
        except TencentLoginError as e:
            logger.warning(str(e))

    def _qrLogin(self) -> dict:
        r = [None]
        sched = self._qr.loop(all_cookie=True)(
            refresh_callback=lambda b: \
                (self.ui.QrExpired if sched.cnt else self.ui.QrFetched)(b),
            return_callback=lambda b: r.__setitem__(0, b),
        )
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

    def login(self) -> str:
        """login and return cookie

        Returns:
            str: cookie

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


class HTTPHelper:
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36 Edg/92.0.902.62"

    def __init__(self, uin, UA=None) -> None:
        self.header = {
            'User-Agent': UA or self.UA,
            "Referer": f"https://user.qzone.qq.com/{uin}", # add referer
            "dnt": "1"
        }
        self.session = requests.Session()

    def post(self, *args, **kwargs):
        r = self.session.post(*args, **kwargs, headers=self.header)
        if r.status_code != 200: raise HTTPError(response=r)
        return r

    def get(self, *args, **kwargs):
        r = self.session.get(*args, **kwargs, headers=self.header)
        if r.status_code != 200: raise HTTPError(response=r)
        return r


def onLoginExpire(e: QzoneError, i, self, *args, **kwargs):
    if e.code != -3000: raise e
    if i == 1: raise e

    logger.info("cookie已过期, 即将重新登陆.")
    QzoneScraper.updateStatus(self, force_login=True)


login_if_expire = Retry({QzoneError: onLoginExpire}, inspect=True)


class QzoneScraper(LoginHelper, HTTPHelper):
    def __init__(
        self,
        token_tbl: TokenTable,
        qq: Union[str, int],
        *,
        password: str = None,
        fetch_times=12,
        qr_strategy='prefer',
        UA=None,
    ):
        qq = int(qq)
        LoginHelper.__init__(self, qq, pwd=password, qr_strategy=qr_strategy)
        HTTPHelper.__init__(self, qq, UA)
        self.fetch_times = fetch_times
        self.db = token_tbl
        self.extern = {1: "undefined"}

    @staticmethod
    def cal_gtk(p_skey):
        phash = 5381
        for i in p_skey:
            phash += (phash << 5) + ord(i)
        return phash & 0x7fffffff

    @staticmethod
    def parseExternParam(unquoted: str) -> dict:
        if unquoted == "undefined": return {}
        dic = {}
        for i in unquoted.split('&'):
            s = i.split('=')
            dic[s[0]] = s[1] if len(s) > 1 else None
        return dic

    def getCompleteFeed(self, feedData: dict) -> str:
        if not feedData: return

        body = {
            "uin": feedData["uin"],
            "tid": feedData["tid"],
            "feedsType": feedData["feedstype"],
            "qzreferrer": f"https://user.qzone.qq.com/{self.uin}",
        }
        body.update(Arg4CompleteFeed)

        r = self.post(COMPLETE_FEED_URL, params={'g_tk': self.gtk}, data=body)

        r = RE_CALLBACK.search(r.text).group(1)
        r = json.loads(r)
        if r["err"] == 0: return r["newFeedXML"].strip()

    def updateStatus(self, force_login=False):
        """
        update cookie, gtk, qzonetoken
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

        self.gtk = self.cal_gtk(cookie["p_skey"])
        self.session.cookies.update(cookie)

    @login_if_expire
    def doLike(self, likedata: dict) -> bool:
        if not hasattr(self, 'gtk'): self.updateStatus()
        body = {
            'qzreferrer': f'https://user.qzone.qq.com/{self.uin}',
            'opuin': self.uin,
            'from': 1,
            'active': 0,
            'fupdate': 1,
            'fid': likedata.pop('key')
        }
        body.update(likedata)
        try:
            r = self.post(DO_LIKE_URL, params={'g_tk': self.gtk}, data=body)
        except HTTPError:
            return False

        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(RE_CALLBACK.search(r).group(1))

        if r["code"] == 0: return True
        else: raise QzoneError(r["code"], r["message"])

    @login_if_expire
    def fetchPage(self, pagenum: int, count: int = 10):
        """
        fetch a page of feeds
        """
        if not hasattr(self, 'gtk'): self.updateStatus()

        query = {
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

        for _ in range(self.fetch_times):
            try:
                r = self.get(GET_PAGE_URL, params=query)
            except HTTPError as e:
                logger.error(f"Http error when fetching page {pagenum}", exc_info=True)
                raise e
            except TypeError as e:
                logger.debug('query = ' + str(query))
                logger.error(
                    'BUG: please report this bug with `query`. thanks.', exc_info=True
                )
                raise e

            r = RE_CALLBACK.search(r.text).group(1)
            r = json_loads(r)
            if r["code"] == -10001:
                logger.info(r["message"])
                time.sleep(5)
            elif r['code'] != 0:
                raise QzoneError(r['code'], r['message'])

            data: dict = r['data']
            self.extern[pagenum + 1] = unquote(data['main']["externparam"])
            feeddict = filter(
                lambda i: not (
                    not i or                                    # `undefined` in feed datas or empty feed dict
                    i['key'].startswith('advertisement_app') or # ad feed
                    int(i['appid']) >= 4096                     # not supported (cannot encode)
                ),
                data['data']
            )
            return list(feeddict)

        raise TimeoutError("network is always busy!")

    @login_if_expire
    def checkUpdate(self):
        r = self.get(UPDATE_FEED_URL, params={'uin': self.uin, 'g_tk': self.gtk})
        r = RE_CALLBACK.search(r.text).group(1)
        r = json_loads(r)
        if r["code"] == 0: return r["data"]
        else: raise QzoneError(r['code'], r['message'])
