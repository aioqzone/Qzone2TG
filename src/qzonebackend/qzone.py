# credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py

import json
import logging
import re
import time
from urllib import parse

import demjson
import requests
import yaml
from tgfrontend.compress import LikeId
from utils import undefined2None

from .common import Args4GettingFeeds, Arg4CompleteFeed
from .qzfeedparser import QZFeedParser as Parser
from .validator.walker import Walker

logger = logging.getLogger("Qzone Scraper")

class QzoneError(RuntimeError):
    def __init__(self, code: int, *args):
        self.code = code
        RuntimeError.__init__(self, *args)

def cal_gtk(p_skey):
    phash = 5381
    for i in p_skey:
        phash += (phash << 5) + ord(i)

    logger.info('生成gtk')
    return phash & 0x7fffffff

def encode_cookie(cookie):
    skip = ["timestamp", "qzonetoken", "gtk"]
    s = '; '.join([k + '=' + v for k, v in cookie.items() if k not in skip])
    return s

def parseExternParam(unquoted: str)-> dict:
    if unquoted == "undefined": return {}
    dic = {}
    for i in unquoted.split('&'):
        s = i.split('=')
        dic[s[0]] = s[1] if len(s) > 1 else None
    return dic

class QzoneScraper:
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66"
    headless = True

    def __init__(self, qq: str, password: str, cookie_expire, selenium_conf, fetch_times = 12, UA=None):
        self.uin = qq
        self.pwd = password
        self.cookie_expire = cookie_expire
        self.selenium_conf = selenium_conf
        self.fetch_times = fetch_times

        self.cookie = ''
        self.extern = {1: "undefined"}

        if UA: self.UA = UA

    @property
    def header(self):
        headers = {
            'User-Agent': self.UA,
            "Referer": "https://user.qzone.qq.com/%d" % self.uin,   # add referer
            "dnt": "1"              # do not trace(Teacher Ma: what you do at gym is not working)
        }
        if self.cookie: headers['Cookie'] = self.cookie
        return headers

    def login(self):
        try:
            return Walker(**self.selenium_conf).login(self.uin, self.pwd)
        except RuntimeError as e:
            logger.error(str(e))

    def getCompleteFeed(self, html: str):
        #TODO: Response 500
        psr = Parser(html)
        if not psr.isCut(): return html
        feed = psr.parseFeedData()
        url = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments?"
        arg = "qzonetoken={qzonetoken}&gtk={gtk}".format(qzonetoken = self.qzonetoken, gtk = self.gtk)
        body = {
            "uin": feed["uin"], 
            "tid": feed["tid"], 
            "feedsType": feed["feedstype"], 
            "qzreferrer": "https://user.qzone.qq.com/%d" % self.uin
        }
        body.update(Arg4CompleteFeed)

        r = requests.post(url + arg, data=body, headers=self.header)
            
        if r.status_code != 200: raise TimeoutError(r.reason)
        # r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(re.search(r"callback\(({.*})", r, re.S | re.I).group(1))
        r = json.loads(r)
        return r["newFeedXML"].strip()
    
    def updateStatus(self, force_login = False):
        """
        update cookie, gtk, qzonetoken
        """

        cookie = {}
        try:
            with open("tmp/cookie.yaml") as f: cookie: dict = yaml.safe_load(f)
        except FileNotFoundError: pass

        t = cookie.get("timestamp", 0)
        if force_login or (time.time() - t) >= self.cookie_expire:
            logger.info("cookie已过期, 重新登陆.")
            cookie = self.login()
            if cookie is None: 
                #TODO fetch QR code
                raise QzoneError(-999, "登陆失败: 您可能被限制账密登陆, 或自动跳过验证失败. 扫码登陆仍然可行.")

            if "p_skey" not in cookie: raise QzoneError(-233, "登陆失败: 或许可以重新登陆.")
            logger.info('取得cookie')
            cookie["timestamp"] = time.time()
            cookie["gtk"] = cal_gtk(cookie["p_skey"])
            with open("tmp/cookie.yaml", "w") as f: yaml.safe_dump(cookie, f)
        else:
            logger.info("使用缓存cookie")

        self.gtk = cookie['gtk']
        self.qzonetoken = cookie["qzonetoken"]
        self.cookie = encode_cookie(cookie)

    def do_like(self, likedata: LikeId)-> bool:
        url = 'https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app?'
        arg = 'g_tk={gtk}&qzonetoken={qzonetoken}'.format(gtk = self.gtk, qzonetoken = self.qzonetoken)

        body = {
            'qzreferrer': 'https://user.qzone.qq.com/%d' % self.uin,
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

        r = requests.post(url + arg, data=body, headers=self.header)
        if r.status_code != 200: return False

        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(re.search(r"callback\(({.*})", r, re.S | re.I).group(1))

        if r["code"] == 0: return True
        else: raise QzoneError(r["code"], r["message"])

    def fetchPage(self, pagenum: int):
        """
        make sure updateStatus is called before.
        """

        url = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more?"
        query = {
            'uin': self.uin, 
            'pagenum': pagenum, 
            'g_tk': self.gtk,
            'begintime': parseExternParam(self.extern[pagenum]).get("basetime", "undefined"),
            'count': 10,
            'usertime': round(time.time() * 1000), 
            'externparam': parse.quote(self.extern[pagenum]), 
            'qzonetoken': self.qzonetoken
        }
        query.update(Args4GettingFeeds)
        url += parse.urlencode(query)

        for i in range(self.fetch_times):

            r = requests.get(url, headers = self.header)

            if r.status_code != 200: raise TimeoutError(r.reason)

            r = re.search(r"callback\(({.*})", r.text, re.S | re.I).group(1)
            r = demjson.decode(r)
            
            if r["code"] == 0:
                data = r['data']['data']
                self.extern[pagenum + 1] = parse.unquote(r['data']['main']["externparam"])
                data = [
                    undefined2None(i) for i in data if not 
                    (
                        i is demjson.undefined 
                        or i['key'].startswith('advertisement_app')
                        or int(i['appid']) >= 4096
                    )
                ]
                return data
            elif r["code"] == -10001:
                logger.info(r["message"])
                time.sleep(5)
            elif r["code"] == -3000:
                raise QzoneError(-3000, r["message"])
            else: 
                raise QzoneError(r['code'], r['message'])
        raise TimeoutError("network is always busy!")
    
    def checkUpdate(self):
        url = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi?"
        arg = parse.urlencode({
            'uin': self.uin,
            'qzonetoken': self.qzonetoken, 
            'g_tk': self.gtk
        })
        r = requests.get(url + arg, headers = self.header)
        r = re.search(r"callback({.*})", r.text, re.S).group(1)
        r = demjson.decode(r)
        if r["code"] == 0: return r["data"]
        else: raise QzoneError(r['code'], r['message'])
