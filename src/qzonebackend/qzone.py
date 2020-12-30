# credits: https://github.com/bufuchangfeng/qzone/blob/master/qzone_with_code.py

import json
import logging
import re
import time
from urllib import parse

import config
import demjson
import requests
import yaml
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from tgfrontend.compress import LikeId

from .htmlparser import HTMLParser as Parser
from .validator.jigsaw import imgcmp

extern = {1: "undefined"}
headers = {
    'User-Agent': config.qzone["UA"],
    "Referer": "https://user.qzone.qq.com/" + config.qzone["qq"],   # add referer
    "dnt": "1"              # do not trace(Teacher Ma: what you do at gym is not working)
}
logger = logging.getLogger("Web Scraper")

class QzoneError(RuntimeError):
    code: int
    def __init__(self, code: int, *args):
        self.code = code
        RuntimeError.__init__(self, *args)

def cal_gtk(p_skey):
    hash = 5381
    for i in p_skey:
        hash += (hash << 5) + ord(i)

    logger.info('生成gtk')
    return hash & 0x7fffffff

def change_cookie(cookie):
    skip = ["timestamp", "qzonetoken", "gtk"]
    s = '; '.join([k + '=' + v for k, v in cookie.items() if k not in skip])
    return s

def login():
    chrome_options = Options()
    #chrome_options.add_argument('--headless')
    chrome_options.add_argument("log-level=%d" % config.qzone["log_level"])
    driver = webdriver.Chrome(options=chrome_options)

    logger.info("等待登陆界面加载")
    driver.get('https://qzone.qq.com/')
    logger.info("登陆界面加载完成")

    driver.switch_to.frame('login_frame')

    driver.find_element_by_id('switcher_plogin').click()
    driver.find_element_by_id('u').clear()
    driver.find_element_by_id('u').send_keys(config.qzone["qq"])
    driver.find_element_by_id('p').clear()
    driver.find_element_by_id('p').send_keys(config.qzone["password"])
    driver.find_element_by_id('login_button').click()

    try:
        WebDriverWait(driver, 3).until(lambda dr: dr.find_element_by_xpath('//*[@id="newVcodeIframe"]/iframe'))
    except NoSuchElementException:
        logger.error("限制登陆.")
        driver.close(); driver.quit()
        return
    else: 
        frame = driver.find_element_by_xpath('//*[@id="newVcodeIframe"]/iframe')
        driver.switch_to.frame(frame)

    WebDriverWait(driver, 3).until(lambda dr: dr.find_element_by_id('slideBg').get_attribute('src'))
    back_url = driver.find_element_by_id('slideBg').get_attribute('src')
    full_url = back_url.replace('hycdn_1', 'hycdn_0')

    w = imgcmp(back_url, full_url)

    if w < 0:
        logger.error("跳过验证失败: 两图完全相同")
        driver.close(); driver.quit()
        return

    slide = driver.find_element_by_id('tcaptcha_drag_thumb')
    ActionChains(driver).click_and_hold(slide).perform()
    ActionChains(driver).move_by_offset(xoffset=w / 700 * 250, yoffset=0).perform()
    ActionChains(driver).release(slide).perform()

    logger.info("等待跳转至Qzone")
    try: WebDriverWait(driver, 5, 0.5, RuntimeError).until(
        lambda dr: ("user.qzone.qq.com/" + config.qzone["qq"]) in driver.current_url, 
        "登陆失败: 未跳转至QZone."
    )
    except RuntimeError as e:
        logger.error(repr(e))
        driver.close(); driver.quit()
        return

    logger.info('跳转成功 (成功混过验证')
    cookie = driver.get_cookies()
    qzonetoken = driver.execute_script('return window.g_qzonetoken')

    # driver.close()
    # driver.quit()

    cookie = {i["name"]: i["value"] for i in cookie}
    cookie["qzonetoken"] = qzonetoken

    return cookie

def getFullContent(html: str, gtk: int, qzonetoken: str):
    #TODO: Response 500
    psr = Parser(html)
    if not psr.hasNext(): return html
    feed = psr.parseFeedData()
    url = "https://user.qzone.qq.com"
    url += "/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_ic_getcomments"
    arg = "?qzonetoken={qzonetoken}&gtk={gtk}".format(qzonetoken = qzonetoken, gtk = gtk)
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
        "qzreferrer": "https://user.qzone.qq.com/" + config.qzone["qq"]
    }

    r = requests.post(url + arg, data=body, headers=headers)
        
    if r.status_code != 200: raise TimeoutError(r.reason)
    r = r.text.replace('\n', '').replace('\t', '')
    r = json.loads(re.search(r"callback\(({.*})", r, re.S | re.I).group(1))
    r = json.loads(r)
    return r["newFeedXML"].strip()
    
def get_args(force_login = False):
    "return (cookie, gtk, qzonetoken)"
    cookie = {}
    try:
        with open("tmp/cookie.yaml") as f: cookie: dict = yaml.load(f)
    except FileNotFoundError: pass

    t = cookie.get("timestamp", 0)
    if force_login or (time.time() - t) >= config.qzone["cookie_expire"]:
        logger.info("cookie expired. relogin start")
        cookie = login()
        if cookie is None: 
            #TODO fetch QR code
            raise RuntimeError("登陆失败: 您可能被限制账密登陆, 或自动跳过验证失败. 扫码登陆仍然可行.")
        if "p_skey" not in cookie: raise RuntimeError("登陆失败: 或许可以重新登陆.")
        logger.info('取得cookie')
        cookie["timestamp"] = time.time()
        cookie["gtk"] = cal_gtk(cookie["p_skey"])
        with open("cookie.yaml", "w") as f: yaml.dump(cookie, f)
    else:
        logger.info("使用缓存cookie")

    gtk = cookie['gtk']
    qzonetoken = cookie["qzonetoken"]
    cookie = change_cookie(cookie)

    return cookie, gtk, qzonetoken


def do_like(likedata: LikeId, gtk: int, qzonetoken: str)-> bool:
    url = 'https://user.qzone.qq.com/'
    url += 'proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app'
    arg = '?g_tk={gtk}&qzonetoken={qzonetoken}'.format(gtk = gtk, qzonetoken = qzonetoken)

    body = {
        'qzreferrer': 'https://user.qzone.qq.com/' + config.qzone["qq"],
        'opuin': config.qzone["qq"],
        'from': 1,
        'active': 0,
        'fupdate': 1
    }

    body['unikey'] = likedata.unikey
    body['curkey'] = likedata.curkey
    body['appid'] = likedata.appid
    body['typeid'] = likedata.typeid
    body['fid'] = likedata.key

    r = requests.post(url + arg, data=body, headers=headers)
    if r.status_code != 200: return False

    r = r.text.replace('\n', '').replace('\t', '')
    r = json.loads(re.search(r"callback\(({.*})", r, re.S | re.I).group(1))

    if r["code"] == 0: return True
    else: raise QzoneError(r["code"], r["message"])

def parseExternParam(unquoted: str)-> dict:
    if unquoted == "undefined": return {}
    dic = {}
    for i in unquoted.split('&'):
        s = i.split('=')
        dic[s[0]] = s[1] if len(s) > 1 else None
    return dic

def get_content(gtk: int, qzonetoken: str, pagenum: int):
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

    global extern

    for i in range(config.qzone["fetch_times"]):
        r = requests.get(url + arg.format(
            uin = config.qzone["qq"], 
            pagenum = pagenum, 
            g_tk = gtk,
            begintime = parseExternParam(extern[pagenum]).get("basetime", "undefined"),
            usertime = int(round(time.time() * 1000)), 
            externparam = parse.quote(extern[pagenum]), 
            qzonetoken = qzonetoken
            ), headers=headers)

        if r.status_code != 200: break

        r = re.search(r"callback\(({.*})", r.text, re.S | re.I).group(1)
        r = eval(repr(r).replace('\\\\', '\\'))
        r = re.sub(r"\\", "", r)
        r = re.sub(r"html:'(.*?)',\s*mergeData:", savehtml, r)
        r = demjson.decode(r)
        
        if r["code"] == 0:
            data = r['data']['data']
            extern[pagenum + 1] = parse.unquote(r['data']['main']["externparam"])
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
    
def check_update(headers: dict, gtk: int, qzonetoken: str):
    url = "https://user.qzone.qq.com"
    url += "/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/cgi_get_feeds_count.cgi?"
    arg = "uin={uin}&qzonetoken={qzonetoken}&g_tk={gtk}"
    r = requests.get(url + arg.format(uin = config.qzone["qq"], qzonetoken = qzonetoken, gtk = gtk), headers = headers)
    r = re.search(r"callback({.*})", r.text, re.S).group(1)
    r = demjson.decode(r)
    if r["code"] == 0: return r["data"]
