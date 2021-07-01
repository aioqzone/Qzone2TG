import logging
import os
import re
import time
from typing import List

import yaml
from tgfrontend.compress import LikeId

from .qzfeedparser import QZFeedParser as Parser
from .qzone import QzoneError, QzoneScraper

logger = logging.getLogger("Feed Manager")
PAGE_LIMIT = 1000


def day_stamp(timestamp: float = None) -> int:
    if timestamp is None: timestamp = time.time()
    return int(timestamp // 86400)


class FeedOperation:
    new_limit = 30

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

    def getFeedsInPage(self, pagenum: int, reload=False):
        self.qzone.updateStatus(reload)
        try:
            feeds = self.qzone.fetchPage(pagenum)
        except QzoneError as e:
            if e.code == -3000 and not reload:
                if not reload:
                    logger.warning("Cookie过期, 强制登陆. 建议修改cookie缓存时间.")
                    self.getFeedsInPage(pagenum, True)
            else:
                raise e

        new = []
        for feed in feeds:
            feed = Parser(feed)

            daystamp = day_stamp(feed.abstime)
            if daystamp + self.keepdays <= day_stamp():
                continue
            folder = f"data/{self.qzone.uin}/{daystamp}"
            os.makedirs(folder, exist_ok=True)
            fname = folder + f"/{feed.hash}.yaml"
            if reload or not os.path.exists(fname):
                if feed.isCut():
                    feed.updateHTML(self.qzone.getCompleteFeed(feed.parseFeedData()))
                new.append(feed)
                feed.dump(fname)

        logger.info(f"获取了{len(feeds)}条说说, {len(new)}条最新")
        return new

    def fetchNewFeeds(self, reload=False):
        try:
            self.cleanFeed()
        except OSError as e:
            logger.error("Failed to clean feed: " + repr(e))

        feeds = []
        for i in range(PAGE_LIMIT):
            tmp = self.getFeedsInPage(i + 1, reload)
            if not tmp: break
            feeds.extend(tmp)
            reload = False
        return sorted(feeds, key=lambda f: f.abstime)

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
