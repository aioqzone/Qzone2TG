import logging
from itertools import takewhile
from math import ceil
from typing import Iterable

from middleware.storage import FeedBase
from middleware.uihook import NullUI
from middleware.utils import day_stamp
from requests.exceptions import HTTPError

from .exceptions import LoginError, UserBreak
from .parser import QzJsonParser as Parser
from .scraper import QzoneScraper

logger = logging.getLogger(__name__)


class FeedDB(FeedBase):
    def getFeed(self, cond_sql: str = '', plugin_name=None, order=False):
        return [
            Parser(i) for i in
            super().getFeed(cond_sql=cond_sql, plugin_name=plugin_name, order=order)
        ]

    def cleanFeed(self):
        return super().cleanFeed(lambda d: Parser(d).getLikeId())

    def dumpFeed(self, feed: Parser, flush=True):
        args = {
            'fid': feed.fid,
            'abstime': feed.abstime,
            'appid': feed.appid,
            'typeid': feed.typeid,
            'nickname': feed.nickname,
            'uin': feed.uin,
            'html': feed.raw['html'],
        }
        self.feed[args['fid']] = args
        if flush: self.db.commit()

    def saveFeeds(self, feeds: Iterable[Parser]):
        for i in feeds:
            self.dumpFeed(i, flush=False)
        self.db.commit()


class QZCachedScraper:
    """Scraper + Database
    """
    hook = NullUI()

    def __init__(self, qzone: QzoneScraper, db: FeedDB):
        self.qzone = qzone
        self.db = db
        self.cleanFeed()

    def register_ui_hook(self, hook: NullUI):
        self.hook = hook
        self.qzone.register_ui_hook(hook)

    def cleanFeed(self):
        self.db.cleanFeed()

    def getNewFeeds(self, pagenum: int, ignore_exist=False):
        """get compelte feeds from qzone and save them to database

        Args:
            `pagenum` (int): page #
            `ignore_exist` (bool, optional): whether to ignore existing feed. Defaults to False.

        Return:
            int: new feeds amount

        Raises:
            UserBreak: see qzone.updateStatus
        """
        try:
            return self._getNewFeeds(pagenum, ignore_exist)
        except KeyboardInterrupt:
            raise UserBreak
        except LoginError as e:
            self.hook.loginFailed(e.args[0])
            return 0
        except Exception as e:
            omit_type = HTTPError,
            logger.error(
                f"{type(e)} when getting page {pagenum}: " + str(e),
                exc_info=not isinstance(e, omit_type),
            )
            return 0

    def _getNewFeeds(self, pagenum: int, ignore_exist=False):
        feeds = self.qzone.fetchPage(pagenum)

        if feeds is None: return 0
        feeds = list(feeds)

        limit = day_stamp() - self.db.keepdays
        new = [
            p for i in feeds
            if ((p := Parser(i)) and ignore_exist or p.fid not in self.db.feed)
            and day_stamp(p.abstime) > limit
        ]
        self.hook.pageFetched(msg := f"获取了{len(feeds)}条说说, {len(new)}条最新")
        logger.info(msg)
        if not new: return 0

        for i in new:
            self.postProcess(i)
            self.db.dumpFeed(i, flush=False)

        self.db.db.commit()

        return len(new)

    def postProcess(self, feed: Parser):
        def complete(i: Parser):
            if not i.isCut(): return
            html = self.qzone.getCompleteFeed(i.feedData)
            if html:
                i.html = html
            else:
                logger.warning(f'feed {i.feedkey}: 获取完整说说失败')

        def album(i: Parser):
            if i.hasAlbum():
                i.parseImage(lambda d, n: self.qzone.photoList(d, i.uin, n))

        for process in [complete, album]:
            process(feed)
        return feed

    def fetchNewFeeds(self, *, no_pred=False, ignore_exist=False):
        """fetch all new feeds.

        Args:
            `no_pred`: do not predict new feeds amount
            `ignore_exist` (bool, optional): Force reload to ignore any feed already in storage. Defaults to False.

        Returns:
            int: new feeds amount
        """
        pred_new = self.qzone.checkUpdate()
        if no_pred or ignore_exist:
            page = 1000
        else:
            if pred_new == 0: return 0
            page = 1 + ceil((pred_new - 5) / 10)

        s = sum(
            takewhile(
                bool, (self._getNewFeeds(i + 1, ignore_exist) for i in range(page))
            )
        )
        if s < pred_new:
            logger.warning(f'Expect to get {pred_new} new feeds, but actually {s}')
        return s

    def like(self, likedata: dict):
        """like a post specified by likedata

        Args:
            likedata (dict): data for do like

        Returns:
            bool: if success
        """
        return self.qzone.doLike(likedata, True)

    def likeAFile(self, fid: str):
        """like a post specified by fid

        Args:
            fid (str): use fid to lookup the storage for likedata

        Raises:
            FileNotFoundError: if fid not exist

        Returns:
            bool: if success
        """
        r = self.db.feed[fid] or self.db.archive[fid]
        if not r: raise FileNotFoundError
        return self.like(Parser(r).getLikeId())
