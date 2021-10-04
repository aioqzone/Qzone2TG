import logging
from itertools import takewhile
from math import ceil

from middleware.storage import PAGE_LIMIT, FeedBase, day_stamp
from middleware.uihook import NullUI
from requests.exceptions import HTTPError
from utils.decorator import classwrapper

from . import QzoneScraper
from .exceptions import LoginError, UserBreak
from .parser import QZFeedParser as Parser

logger = logging.getLogger(__name__)


class QZCachedScraper:
    """Scraper + Database
    """
    ui = NullUI()

    def __init__(self, qzone: QzoneScraper, db: FeedBase):
        self.qzone = qzone
        self.db = db
        self.cleanFeed()

    def register_ui_hook(self, ui: NullUI):
        self.ui = ui

    def cleanFeed(self):
        self.db.cleanFeed()

    @classwrapper
    def _logexc(self, func, pagenum: int, ignore_exist=False):
        try:
            return func(self, pagenum, ignore_exist)
        except KeyboardInterrupt:
            raise UserBreak
        except Exception as e:
            omit_type = [HTTPError, LoginError]
            logger.error(
                f"{type(e)} when getting page {pagenum}: " + str(e),
                exc_info=not isinstance(e, omit_type),
            )
            return 0

    @_logexc
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
        feeds = self.qzone.fetchPage(pagenum)

        if feeds is None: return 0
        feeds = list(feeds)

        limit = day_stamp() - self.db.keepdays
        new = [
            p for i in feeds
            if ((p := Parser(i)) and ignore_exist or p.fid not in self.db.feed)
            and day_stamp(p.abstime) > limit
        ]
        self.ui.pageFetched(msg := f"获取了{len(feeds)}条说说, {len(new)}条最新")
        logger.info(msg)
        if not new: return 0

        for i in new:
            if not i.isCut(): continue
            html = self.qzone.getCompleteFeed(i.parseFeedData())
            if html:
                i.updateHTML(html)
            else:
                logger.warning(f'feed {i.feedkey}: 获取完整说说失败')

        self.db.saveFeeds(new)
        return len(new)

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
                bool, (self.getNewFeeds(i + 1, ignore_exist) for i in range(page))
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
        return self.qzone.doLike(likedata)

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
