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

from .htmlparser import HTMLParser as Parser
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

def change_cookie(cookie):
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

    def __init__(self, qq: str, password: str, cookie_expire, log_level, fetch_times = 12, UA=None):
        self.uin = qq
        self.pwd = password
        self.cookie_expire = cookie_expire
        self.log_level = log_level
        self.fetch_times = fetch_times

        self.cookie = ''
        self.extern = {1: "undefined"}

        if UA: self.UA = UA

    @property
    def header(self):
        headers = {
            'User-Agent': self.UA,
            "Referer": "https://user.qzone.qq.com/" + self.uin,   # add referer
            "dnt": "1"              # do not trace(Teacher Ma: what you do at gym is not working)
        }
        if self.cookie: headers['Cookie'] = self.cookie
        return headers

    def login(self):
        try:
            return Walker(executable_path='msedgedriver.exe').login(self.uin, self.pwd)
        except RuntimeError as e:
            logger.error(str(e))

    def getFullContent(self, html: str):
        #TODO: Response 500
        psr = Parser(html)
        if not psr.hasNext(): return html
        feed = psr.parseFeedData()
        url = "https://user.qzone.qq.com"
        url += "/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
        arg = "?qzonetoken={qzonetoken}&gtk={gtk}".format(qzonetoken = self.qzonetoken, gtk = self.gtk)
        body = {
            "uin": feed["uin"], 
            "pos": 0, 
            "num": 1,
            "cmtnum": 1, 
            "t1_source": 1, 
            "tid": feed["tid"], 
            "who": 1, 
            "inCharset": "utf-8", 
            "outCharset": "utf-8", 
            "plat": "qzone", 
            "source": "ic", 
            "paramstr": 1, 
            "feedsType": feed["feedstype"], 
            "fullContent": 1, 
            "qzreferrer": "https://user.qzone.qq.com/" + self.uin
        }

        r = requests.post(url + arg, data=body, headers=self.header)
            
        if r.status_code != 200: raise TimeoutError(r.reason)
        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(re.search(r"callback\(({.*})", r, re.S | re.I).group(1))
        r = json.loads(r)
        return r["newFeedXML"].strip()
    
    def updateStatus(self, force_login = False):
        """
        update cookie, gtk, qzonetoken
        """

        cookie = {}
        try:
            with open("tmp/cookie.yaml") as f: cookie: dict = yaml.load(f)
        except FileNotFoundError: pass

        t = cookie.get("timestamp", 0)
        if force_login or (time.time() - t) >= self.cookie_expire:
            logger.info("cookie expired. relogin start")
            cookie = self.login()
            if cookie is None: 
                #TODO fetch QR code
                raise RuntimeError("登陆失败: 您可能被限制账密登陆, 或自动跳过验证失败. 扫码登陆仍然可行.")
            if "p_skey" not in cookie: raise RuntimeError("登陆失败: 或许可以重新登陆.")
            logger.info('取得cookie')
            cookie["timestamp"] = time.time()
            cookie["gtk"] = cal_gtk(cookie["p_skey"])
            with open("tmp/cookie.yaml", "w") as f: yaml.dump(cookie, f)
        else:
            logger.info("使用缓存cookie")

        self.gtk = cookie['gtk']
        self.qzonetoken = cookie["qzonetoken"]
        self.cookie = change_cookie(cookie)

    def do_like(self, likedata: LikeId)-> bool:
        url = 'https://user.qzone.qq.com/'
        url += 'proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app'
        arg = '?g_tk={gtk}&qzonetoken={qzonetoken}'.format(gtk = self.gtk, qzonetoken = self.qzonetoken)

        body = {
            'qzreferrer': 'https://user.qzone.qq.com/' + self.uin,
            'opuin': self.uin,
            'from': 1,
            'active': 0,
            'fupdate': 1
        }

        body['unikey'] = likedata.unikey
        body['curkey'] = likedata.curkey
        body['appid'] = likedata.appid
        body['typeid'] = likedata.typeid
        body['fid'] = likedata.key

        r = requests.post(url + arg, data=body, headers=self.header)
        if r.status_code != 200: return False

        r = r.text.replace('\n', '').replace('\t', '')
        r = json.loads(re.search(r"callback\(({.*})", r, re.S | re.I).group(1))

        if r["code"] == 0: return True
        else: raise QzoneError(r["code"], r["message"])

    def get_content(self, pagenum: int):
        url = "https://user.qzone.qq.com"
        url += "/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more?uin={uin}&scope=0&view=1&daylist=&uinlist=&gid=&flag=1"
        arg = "&filter=all&applist=all&refresh=0&aisortEndTime=0&aisortOffset=0&getAisort=0&aisortBeginTime=0&pagenum={pagenum}"
        arg += "&externparam={externparam}&firstGetGroup=0&icServerTime=0&mixnocache=0&scene=0&begintime={begintime}&count=10&dayspac=undefined"
        arg += "&sidomain=qzonestyle.gtimg.cn&useutf8=1&outputhtmlfeed=1&usertime={usertime}&qzonetoken={qzonetoken}&g_tk={g_tk}"
        data = []
        html = []
        def savehtml(m: re.Match):
            html.append(m.group(1).strip())
            return "html:%d,mergeData:" % (len(html) - 1)

        for i in range(self.fetch_times):
            r = requests.get(url + arg.format(
                uin = self.uin, 
                pagenum = pagenum, 
                g_tk = self.gtk,
                begintime = parseExternParam(self.extern[pagenum]).get("basetime", "undefined"),
                usertime = int(round(time.time() * 1000)), 
                externparam = parse.quote(self.extern[pagenum]), 
                qzonetoken = self.qzonetoken
                ), headers = self.header)

            if r.status_code != 200: break

            r = re.search(r"callback\(({.*})", r.text, re.S | re.I).group(1)
            r = eval(repr(r).replace('\\\\', '\\'))
            r = re.sub(r"\\", "", r)
            r = re.sub(r"html:'(.*?)',\s*mergeData:", savehtml, r)
            r = demjson.decode(r)
            
            if r["code"] == 0:
                data = r['data']['data']
                self.extern[pagenum + 1] = parse.unquote(r['data']['main']["externparam"])
                data = [
                    i for i in data if not 
                    (
                        i is demjson.undefined 
                        or i['key'].startswith('advertisement_app')
                        or int(i['appid']) >= 4096
                    )
                ]
                for i, h in zip(data, html): i["html"] = html[i["html"]]
                return data
            elif r["code"] == -10001:
                logger.info(r["message"])
                time.sleep(5)
            elif r["code"] == -3000:
                raise QzoneError(-3000, r["message"])
            else: 
                raise QzoneError(r['code'], r['message'])
        raise TimeoutError("network is always busy!")
    
    def checkUpdate(self, headers: dict):
        url = "https://user.qzone.qq.com"
        url += "/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi?"
        arg = "uin={uin}&qzonetoken={qzonetoken}&g_tk={gtk}"
        r = requests.get(
            url + arg.format(uin = self.uin, qzonetoken = self.qzonetoken, gtk = self.gtk), 
            headers = headers
        )
        r = re.search(r"callback({.*})", r.text, re.S).group(1)
        r = demjson.decode(r)
        if r["code"] == 0: return r["data"]
        else: raise QzoneError(r['code'], r['message'])