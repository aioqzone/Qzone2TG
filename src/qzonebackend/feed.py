import yaml
import logging
import os
import re
import time
from .qzfeedparser import QZFeedParser as Parser

from demjson import undefined

from tgfrontend.compress import LikeId
from .qzone import QzoneError, QzoneScraper

logger = logging.getLogger("Feed Manager")


def make_hash(feed: dict) -> int:
    return hash((int(feed["uin"]), int(feed["abstime"])))


def day_stamp(timestamp: float = None) -> int:
    if timestamp is None: timestamp = time.time()
    return int(timestamp // 86400)


class FeedOperation:
    def __init__(self, qzone: QzoneScraper, keepdays=3):
        self.keepdays = keepdays
        self.qzone = qzone

    def cleanFeed(self):
        if not os.path.exists("data"): return
        ls = lambda f: [f + '/' + i for i in os.listdir(f)]
        accounts = ls("data")
        files = sum([ls(i) for i in accounts], [])

        pattern = re.compile(r"/(\d+)$")
        dic = {}
        for i in files:
            daystamp = int(pattern.search(i).group(1))
            if daystamp in dic: dic[daystamp].append(i)
            else: dic[daystamp] = [i]
        daystamp = day_stamp()
        for k, v in dic.items():
            if k + self.keepdays <= daystamp:
                for f in v:
                    for i in ls(f):
                        os.remove(i)
                    os.removedirs(f)
                    logger.info("clean folder: " + f)

    def getFeeds(self, pagenum: int, reload=False):

        for i in range(2):
            if i == 1: logger.info("force relogin")
            try:
                feeds = self.qzone.fetchPage(pagenum)
            except QzoneError as e:
                if e.code == -3000: logger.warning("Cookie过期, 强制登陆. 建议修改cookie缓存时间.")
                else: raise e
            else: break

        hasnext = True
        new = 0
        for i in feeds:
            i["hash"] = make_hash(i)
            daystamp = day_stamp(int(i["abstime"]))
            if daystamp + self.keepdays <= day_stamp():
                hasnext = False
                break
            folder = "data/%s/%d" % (self.qzone.uin, daystamp)
            if not os.path.exists(folder): os.makedirs(folder)
            fname = folder + "/%s.yaml" % i["hash"]
            if (not reload) and os.path.exists(fname):
                hasnext = False
                break
            else:
                new += 1
                with open(fname, "w", encoding='utf-8') as f:
                    yaml.dump(i, f)            # TODO: maybe need to override the dumper

        logger.info("获取了%d条说说, %d条最新" % (len(feeds), new))
        feeds = feeds[:new]
        return hasnext, feeds

    def fetchNewFeeds(self, reload=False):
        try:
            self.cleanFeed()
        except OSError as e:
            logger.error("Failed to clean feed: " + repr(e))

        i = 0
        hasnext = True
        feeds = []
        while hasnext:
            i += 1
            hasnext, tmp = self.getFeeds(i, reload)
            feeds.extend(tmp)
        return sorted(feeds, key=lambda f: f["abstime"])

    def like(self, likedata: LikeId):
        self.qzone.updateStatus()
        return self.qzone.do_like(likedata)

    def likeAFile(self, fname: str) -> bool:
        feed = {}

        if not os.path.exists(fname): raise FileNotFoundError(fname)
        with open(fname) as f:
            feed = yaml.load(f)

        psr = Parser(feed)
        return self.like(LikeId(psr.appid, psr.typeid, feed['key'], *psr.uckeys))
