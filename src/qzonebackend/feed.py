import logging
import os
import re
import time

import yaml
from requests.exceptions import HTTPError
from tgfrontend.compress import LikeId
from uihook import NullUI

from .qzfeedparser import QZFeedParser as Parser
from .qzone import LoginError, QzoneScraper

logger = logging.getLogger("Feed Manager")
PAGE_LIMIT = 1000


def day_stamp(timestamp: float = None) -> int:
    if timestamp is None: timestamp = time.time()
    return int(timestamp // 86400)


class FeedMgr:
    def __init__(self, uin, keepdays=3) -> None:
        self.uin = uin
        self.keepdays = keepdays

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

    @staticmethod
    def dumpFeed(feed: Parser, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            return yaml.safe_dump({k: v for k, v in feed.raw.items() if v}, f)

    @staticmethod
    def fromFile(fname):
        with open(fname, encoding='utf8') as f:
            feed = yaml.safe_load(f)
            return Parser(feed)

    def saveFeed(self, feed: Parser, force=False, get_complete_callback=None):
        daystamp = day_stamp(feed.abstime)
        if daystamp + self.keepdays <= day_stamp():
            return False

        folder = f"data/{self.uin}/{daystamp}"
        os.makedirs(folder, exist_ok=True)
        fname = folder + f"/{feed.hash}.yaml"
        if force or not os.path.exists(fname):
            if get_complete_callback and feed.isCut():
                feed.updateHTML(get_complete_callback(feed.parseFeedData()))
            self.dumpFeed(feed, fname)
            return True
        return False


class QZCachedScraper(FeedMgr):
    new_limit = 30         # not implement

    def __init__(self, qzone: QzoneScraper, keepdays=3):
        self.qzone = qzone
        FeedMgr.__init__(self, qzone.uin, keepdays)

    def register_ui_hook(self, ui: NullUI):
        self.ui = ui

    def getFeedsInPage(self, pagenum: int, reload=False, retry=1):
        try:
            self.qzone.updateStatus(reload)
            feeds = self.qzone.fetchPage(pagenum)
        except HTTPError as e:
            if e.response.status_code == 403 and retry > 0:
                return self.getFeedsInPage(pagenum, reload=reload, retry=retry - 1)
            else:
                raise e
        except LoginError:
            logger.error(
                f'Error fetch page {pagenum}{", force reload" if reload else ""}',
                exc_info=True
            )
            return []
        except Exception:
            logger.error(
                f'Error fetch page {pagenum}{", force reload" if reload else ""}, retry remains={retry}',
                exc_info=True
            )

        new = [
            feed for i in feeds if self.saveFeed(
                (feed := Parser(i)),
                force=reload,
                get_complete_callback=self.qzone.getCompleteFeed,
            )
        ]

        self.ui.pageFetched(msg := f"获取了{len(feeds)}条说说, {len(new)}条最新")
        logger.info(msg)
        return new

    def fetchNewFeeds(self, reload=False):
        feeds = []
        for i in range(PAGE_LIMIT):
            tmp = self.getFeedsInPage(i + 1, reload)
            if not tmp: break
            feeds.extend(tmp)
            reload = False
        return sorted(feeds, key=lambda f: f.abstime)

    def like(self, likedata: LikeId):
        return self.qzone.doLike(likedata)

    def likeAFile(self, fname: str) -> bool:
        return self.like(self.fromFile(fname).getLikeId())
