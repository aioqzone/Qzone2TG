"""
qzone: 
    Fetch feeds from qzone, Along with qzone login and cookie management.
    
    credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py
"""

import json
import logging
import os
import re
import time
from typing import Union
from urllib.parse import quote, unquote

import requests
import yaml
from requests.exceptions import HTTPError
from tencentlogin.constants import QzoneAppid, QzoneProxy
from tencentlogin.qr import QRLogin
from tencentlogin.up import UPLogin, User
from tgfrontend.compress import LikeId
from uihook import NullUI

from . import QzoneError
from .common import *
from .regjson import json_loads

logger = logging.getLogger("Qzone Scraper")

PROXY_DOMAIN = "https://user.qzone.qq.com/proxy/domain"
COMPLETE_FEED_URL = PROXY_DOMAIN + "/taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
DO_LIKE_URL = PROXY_DOMAIN + "/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
GET_PAGE_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
UPDATE_FEED_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi"

RE_CALLBACK = re.compile(r"callback\((\{.*\})", re.S | re.I)


class LoginHelper:
    def __init__(self, uin: int, *, pwd: str = None, qr_strategy='prefer') -> None:
        self.uin = uin
        self.pwd = pwd
        self.qr_strategy = qr_strategy

    def register_ui_hook(self, ui: NullUI):
        self.ui = ui

    def _upLogin(self):
        t = UPLogin(QzoneAppid, QzoneProxy, User(self.uin, self.pwd))
        r = t.check()
        if r[0] == 0: return t.login(r, all_cookie=True)

    def _qrLogin(self):
        t = QRLogin(QzoneAppid, QzoneProxy)
        try:
            for i, png in enumerate(t.loop(all_cookie=True)):
                if isinstance(png, bytes):
                    (self.ui.QrExpired if i else self.ui.QrFetched)(png)
        except TimeoutError:
            return
        else:
            self.ui.QrScanSucceessed()
            return png

    def login(self) -> str:
        """login and return cookie

        Returns:
            str: cookie
        """
        if self.qr_strategy == 'force':
            return self._qrLogin()

        elif self.qr_strategy == 'prefer':
            if not (cookie := self._qrLogin()):
                return self._upLogin()

        elif self.qr_strategy == 'allow':
            if not (cookie := self._upLogin):
                return self._qrLogin()

        elif self.qr_strategy == 'forbid':
            return self._upLogin()

        else:
            raise ValueError(self.qr_strategy)
        return cookie


class HTTPHelper:
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66"

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


class QzoneScraper(LoginHelper, HTTPHelper):
    COOKIE_CACHE = 'tmp/cookie.yml'

    def __init__(
        self,
        qq: Union[str, int],
        *,
        password: str = None,
        fetch_times=12,
        qr_strategy='prefer',
        UA=None,
        cookie_cache=None,
    ):
        qq = int(qq)
        LoginHelper.__init__(self, qq, pwd=password, qr_strategy=qr_strategy)
        HTTPHelper.__init__(self, qq, UA)
        self.fetch_times = fetch_times
        self.extern = {1: "undefined"}
        self.COOKIE_CACHE = cookie_cache or self.COOKIE_CACHE

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
        return r["newFeedXML"].strip()

    def updateStatus(self, force_login=False):
        """
        update cookie, gtk, qzonetoken
        """
        if os.path.exists(self.COOKIE_CACHE):
            with open(self.COOKIE_CACHE) as f:
                cookie: dict = yaml.safe_load(f)
            if self.uin in cookie:
                cookie = cookie[self.uin]
            else:
                force_login = True
        else:
            force_login = True
            os.makedirs(os.path.dirname(self.COOKIE_CACHE), exist_ok=True)

        if force_login:
            logger.info("重新登陆.")
            cookie = self.login()

            e = None
            if cookie is None:
                if self.qr_strategy == 'forbid':
                    e = RuntimeError("登陆失败: 您可能被限制账密登陆, 或自动跳过验证失败. 扫码登陆仍然可行.")
                else:
                    e = RuntimeError("登陆失败: 您可能被限制登陆, 或自动跳过验证失败.")
            elif "p_skey" not in cookie:
                e = RuntimeError("登陆失败: 或许可以重新登陆.")
            if e:
                self.ui.loginFailed(e.args[0])
                raise e

            logger.info('取得cookie')
            self.ui.loginSuccessed()

            with open(self.COOKIE_CACHE, "w") as f:
                yaml.safe_dump({self.uin: cookie}, f)
        else:
            logger.info("使用缓存cookie")

        self.gtk = self.cal_gtk(cookie["p_skey"])
        self.session.cookies.update(cookie)

    def doLike(self, likedata: LikeId) -> bool:
        if not hasattr(self, 'gtk'): self.updateStatus()
        body = {
            'qzreferrer': f'https://user.qzone.qq.com/{self.uin}',
            'opuin': self.uin,
            'unikey': likedata.unikey,
            'curkey': likedata.curkey,
            'appid': likedata.appid,
            'typeid': likedata.typeid,
            'fid': likedata.fid,
            'from': 1,
            'active': 0,
            'fupdate': 1
        }
        try:
            r = self.post(DO_LIKE_URL, params={'g_tk': self.gtk}, data=body)
        except HTTPError:
            return False

        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(RE_CALLBACK.search(r).group(1))

        if r["code"] == 0: return True
        else: raise QzoneError(r["code"], r["message"])

    def fetchPage(self, pagenum: int, count: int = 10):
        """
        make sure updateStatus is called before.
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

            r = RE_CALLBACK.search(r.text).group(1)
            r = json_loads(r)

            def OK():
                nonlocal r
                data: dict = r['data']
                self.extern[pagenum + 1] = unquote(data['main']["externparam"])
                feeddict = filter(
                    lambda i: not (
                        not i or                                    # `undefined` in feed datas or empty feed dict
                        i['key'].startswith('advertisement_app') or # ad feed
                        int(i['appid']) >=
                        4096                                        # not supported (cannot encode), this might be removed
                    ),
                    data['data']
                )
                return list(feeddict)

            def Expire():
                logger.info("cookie已过期, 即将重新登陆.")
                self.updateStatus(True)
                return self.fetchPage(pagenum=pagenum, count=count)

            if r['code'] in [0, -3000]:
                return {0: OK, -3000: Expire}[r['code']]()
            elif r["code"] == -10001:
                logger.info(r["message"])
                time.sleep(5)
            else:
                raise QzoneError(r['code'], r['message'])

        raise TimeoutError("network is always busy!")

    def checkUpdate(self):
        r = self.get(UPDATE_FEED_URL, params={'uin': self.uin, 'g_tk': self.gtk})
        r = RE_CALLBACK.search(r.text).group(1)
        r = json_loads(r)
        if r["code"] == 0: return r["data"]
        else: raise QzoneError(r['code'], r['message'])
