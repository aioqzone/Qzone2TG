# credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py

import json
import logging
import os
import re
import time
from urllib.parse import quote, unquote

import demjson
import requests
import yaml
from requests.exceptions import HTTPError
from tgfrontend.compress import LikeId
from utils import undefined2None

from .common import Arg4CompleteFeed, Args4GettingFeeds
from .validator.walker import Walker

logger = logging.getLogger("Qzone Scraper")

PROXY_DOMAIN = "https://user.qzone.qq.com/proxy/domain"
COMPLETE_FEED_URL = PROXY_DOMAIN + "/taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
DO_LIKE_URL = PROXY_DOMAIN + "/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
GET_PAGE_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
UPDATE_FEED_URL = PROXY_DOMAIN + "/ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi"

RE_CALLBACK = re.compile(r"callback\((\{.*\})", re.S | re.I)


class QzoneError(RuntimeError):
    def __init__(self, code: int, *args):
        self.code = int(code)
        RuntimeError.__init__(self, *args)


def cal_gtk(p_skey):
    phash = 5381
    for i in p_skey:
        phash += (phash << 5) + ord(i)

    logger.info('生成gtk')
    return phash & 0x7fffffff


def parseExternParam(unquoted: str) -> dict:
    if unquoted == "undefined": return {}
    dic = {}
    for i in unquoted.split('&'):
        s = i.split('=')
        dic[s[0]] = s[1] if len(s) > 1 else None
    return dic


class QzoneScraper:
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66"
    headless = True
    COOKIE_CACHE = 'tmp/cookie.yaml'

    def __init__(
        self,
        qq: str,
        *,
        cookie_expire: int = 3,
        selenium_conf: dict = None,
        password: str = None,
        fetch_times=12,
        qr_strategy='prefer',
        UA=None,
        cookie_cache=None,
    ):
        self.session = requests.Session()
        self.uin = qq
        self.pwd = password
        self.cookie_expire = cookie_expire
        self.selenium_conf = selenium_conf
        self.fetch_times = fetch_times
        self.qr_strategy = qr_strategy

        self.extern = {1: "undefined"}

        if UA: self.UA = UA
        if cookie_cache: self.COOKIE_CACHE = cookie_cache

        self.header = {
            'User-Agent': self.UA,
            "Referer": "https://user.qzone.qq.com/%d" % self.uin, # add referer
            "dnt": "1"
        }

    def post(self, *args, **kwargs):
        r = self.session.post(*args, **kwargs, headers=self.header)
        if r.status_code != 200: raise HTTPError(response=r)
        return r

    def get(self, *args, **kwargs):
        r = self.session.get(*args, **kwargs, headers=self.header)
        if r.status_code != 200: raise HTTPError(response=r)
        return r

    def register_qr_callback(self, qr_url_callback: callable):
        self.qr_url_callback = qr_url_callback

    def login(self) -> str:
        """login and return cookie

        Returns:
            str: cookie
        """
        try:
            walker = Walker(**self.selenium_conf, qr_strategy=self.qr_strategy)
            walker.register_qr_callback(self.qr_url_callback)
            return walker.login(self.uin, self.pwd)
        except RuntimeError as e:
            logger.error(str(e))

    def getCompleteFeed(self, feedData: dict) -> str:
        body = {
            "uin": feedData["uin"],
            "tid": feedData["tid"],
            "feedsType": feedData["feedstype"],
            "qzreferrer": f"https://user.qzone.qq.com/{self.uin}",
        }
        body.update(Arg4CompleteFeed)

        r = self.post(COMPLETE_FEED_URL, params={'g_tk': self.gtk}, data=body)

        # TODO: Response 500
        r = RE_CALLBACK.search(r.text).group(1)
        r = json.loads(r)
        return r["newFeedXML"].strip()

    def updateStatus(self, force_login=False):
        """
        update cookie, gtk, qzonetoken
        """
        cookie = {}

        if os.path.exists(self.COOKIE_CACHE):
            with open(self.COOKIE_CACHE) as f:
                cookie: dict = yaml.safe_load(f)

        t = cookie.get("timestamp", 0)
        if (time.time() - t) >= self.cookie_expire:
            logger.info("cookie已过期, 即将重新登陆.")
            force_login = True

        if force_login:
            logger.info("重新登陆.")
            cookie = self.login()
            if cookie is None:
                if self.qr_strategy == 'forbid':
                    raise RuntimeError("登陆失败: 您可能被限制账密登陆, 或自动跳过验证失败. 扫码登陆仍然可行.")
                else:
                    raise RuntimeError("登陆失败: 您可能被限制登陆, 或自动跳过验证失败.")

            if "p_skey" not in cookie: raise RuntimeError("登陆失败: 或许可以重新登陆.")
            logger.info('取得cookie')
            cookie["timestamp"] = time.time()
            cookie["gtk"] = cal_gtk(cookie["p_skey"])
            if self.cookie_expire > 0:
                with open(self.COOKIE_CACHE, "w") as f:
                    yaml.safe_dump(cookie, f)
        else:
            logger.info("使用缓存cookie")

        self.gtk = cookie['gtk']
        for k in ['gtk', 'timestamp']:
            cookie[k] = str(cookie[k])
        self.session.cookies.update(cookie)

    def do_like(self, likedata: LikeId) -> bool:
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
        assert hasattr(self, 'gtk'), 'updateStatus should be called before.'

        query = {
            'uin': self.uin,
            'pagenum': pagenum,
            'g_tk': self.gtk,
            'begintime': parseExternParam(self.extern[pagenum]
                                          ).get("basetime", "undefined"),
            'count': count,
            'usertime': round(time.time() * 1000),
            'externparam': quote(self.extern[pagenum])
        }
        query.update(Args4GettingFeeds)

        for _ in range(self.fetch_times):
            r = self.get(GET_PAGE_URL, params=query)
            r = RE_CALLBACK.search(r.text).group(1)
            r = demjson.decode(r)

            if r["code"] == 0:
                data: dict = r['data']
                self.extern[pagenum + 1] = unquote(data['main']["externparam"])
                feeddict = filter(
                    lambda i: not (
                        i is demjson.undefined or \
                        i['key'].startswith('advertisement_app') or \
                        int(i['appid']) >= 4096
                    ), data['data']
                )
                return [undefined2None(i) for i in feeddict]
            elif r["code"] == -10001:
                logger.info(r["message"])
                time.sleep(5)
            elif r["code"] == -3000:
                # TODO
                raise QzoneError(-3000, r["message"])
            else:
                raise QzoneError(r['code'], r['message'])
        raise TimeoutError("network is always busy!")

    def checkUpdate(self):
        r = self.get(UPDATE_FEED_URL, params={'uin': self.uin, 'g_tk': self.gtk})
        r = RE_CALLBACK.search(r.text).group(1)
        r = demjson.decode(r)
        if r["code"] == 0: return r["data"]
        else: raise QzoneError(r['code'], r['message'])
