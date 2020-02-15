import json
import logging
import os
import re
import time
from HTMLParser import HTMLParser as parser

from demjson import undefined

import config
import qzone
from compress import LikeId
from qzone import QzoneError, do_like, get_args, get_content

logger = logging.getLogger(__name__)

headers = {
    'User-Agent': config.qzone["UA"],
    "Referer": "https://user.qzone.qq.com/" + config.qzone["qq"],   # add referer
    "dnt": "1"                                           # do not trace
}

def make_hash(feed: dict)-> int:
    return hash((
        int(feed["uin"]), 
        int(feed["abstime"])
    ))

def day_stamp(timestamp: float = None)-> int:
    if timestamp is None: timestamp = time.time()
    return int(timestamp // 86400)

def cleanFeed():
    if not os.path.exists("feeds"): return
    ls = lambda f: [f + '/' + i for i in os.listdir(f)]
    keep = config.feed.get("keepdays", 3)
    accounts = ls("feeds")
    files = sum([ls(i) for i in accounts], [])
    
    pattern = re.compile(r"/(\d+)$")
    dic = {}
    for i in files:
        daystamp = int(pattern.search(i).group(1))
        if daystamp in dic: dic[daystamp].append(i)
        else: dic[daystamp] = [i]
    daystamp = day_stamp()
    for k, v in dic.items():
        if k + keep <= daystamp:
            for f in v: 
                for i in ls(f): os.remove(i)
                os.removedirs(f)
                logger.info("clean folder: " + f)

class jsonDumper(json.JSONEncoder):
    def default(self, obj):
        if obj == undefined: return "undefined"
        else: return json.JSONEncoder.default(self, obj)

def getFeeds(pagenum: int, headers: dict, reload = False):

    for i in range(2):
        if i == 1: logger.info("force relogin")
        cookie, gtk, qzonetoken = get_args(bool(i))
        headers['Cookie'] = cookie

        try:
            feeds = get_content(headers, gtk, qzonetoken, pagenum)
        except QzoneError as e:
            if e.code == -3000: logger.warning("Cookie过期, 强制登陆. 建议修改cookie缓存时间.")
            else: raise e
        else: break

    hasnext = True
    new = 0
    for i in feeds:
        i["hash"] = make_hash(i)
        daystamp = day_stamp(int(i["abstime"]))
        if daystamp + config.feed["keepdays"] <= day_stamp(): 
            hasnext = False
            break
        folder = "feeds/%s/%d" % (config.qzone["qq"], daystamp)
        if not os.path.exists(folder): os.makedirs(folder)
        fname = folder + "/%s.json" % i["hash"]
        if (not reload) and os.path.exists(fname): 
            hasnext = False
            break
        else:
            new += 1
            with open(fname, "w", encoding='utf-8') as f: json.dump(i, f, cls = jsonDumper)

    logger.info("获取了%d条说说, %d条最新" % (len(feeds), new))
    feeds = feeds[:new]
    return hasnext, feeds

def fetchNewFeeds(reload = False):
    try: cleanFeed()
    except OSError as e: 
        logger.error("Failed to clean feed: " + repr(e))
        
    i = 0
    hasnext = True
    feeds = []
    while hasnext:
        i += 1
        hasnext, tmp = getFeeds(i, headers, reload)
        feeds.extend(tmp)
    return sorted(feeds, key=lambda f: f["abstime"])

def like(likedata: LikeId):
    cookie, gtk, qzonetoken = get_args()
    qzone.headers["Cookie"] = cookie
    return do_like(likedata, gtk, qzonetoken)

def likeAFile(fname: str)-> bool:
    feed = {}

    if not os.path.exists(fname): raise FileNotFoundError(fname)
    with open(fname) as f: feed = json.load(f)

    psr = parser(feed['html'])
    return like(LikeId(int(feed['appid']), int(feed['typeid']), feed['key'], psr.unikey(), psr.curkey()))
