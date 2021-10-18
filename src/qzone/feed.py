import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import takewhile
from math import ceil
from typing import Iterable, Union

from middleware.storage import FeedBase
from middleware.uihook import NullUI
from middleware.utils import day_stamp
from requests.exceptions import HTTPError
from utils.decorator import noexcept

from .exceptions import LoginError, QzoneError, UserBreak
from .parser import QzJsonParser as Parser
from .scraper import QzoneScraper

logger = logging.getLogger(__name__)


class FeedDB(FeedBase):
    def __init__(
        self,
        db,
        keepdays: int = 3,
        archivedays: int = 180,
        plugins: dict = None
    ) -> None:
        super().__init__(
            db,
            keepdays=keepdays,
            archivedays=archivedays,
            plugins=plugins,
            thread_safe=True
        )

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
            'html': feed.html,
        }
        self.feed[args['fid']] = args
        if flush: self.db.commit()
        return feed

    def saveFeeds(self, feeds: Iterable[Parser]):
        for i in feeds:
            self.dumpFeed(i, flush=False)
        self.db.commit()


class QZCachedScraper:
    """Scraper + Database
    """
    hook = NullUI()

    def __init__(self, qzone: QzoneScraper, db: FeedDB, max_worker=None):
        self.qzone = qzone
        self.db = db
        self.cleanFeed()
        self.executor = ThreadPoolExecutor(max_worker, thread_name_prefix='qzdb')

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
            All exceptions qzone.scraper.fetchPage have:

            `UserBreak`: see `updateStatus`
            `LoginError`: see `updateStatus`
            `HTTPError`: as it is
            `QzoneError`: exceptions that are raised by Qzone
            `TimeoutError`: if code -10001 is returned for 12 times.
        """
        feeds = self.qzone.fetchPage(pagenum)
        if feeds is None: return 0

        limit = day_stamp() - self.db.keepdays

        @noexcept({
            BaseException: lambda _: logger.
            error('Expt in concurrent context.', exc_info=True)
        })
        def concurrent(i: dict):
            # a coarse concurrency. need further optimization.
            feed = Parser(i)
            if day_stamp(feed.abstime) < limit: return
            if not ignore_exist and feed.fid in self.db.feed: return
            return self.db.dumpFeed(self.postProcess(feed), flush=False)

        # To avoid any unexpected behavior, `concurrent` should be noexcept.
        new = self.executor.map(concurrent, feeds)
        self.db.db.commit()

        new = list(filter(None, new))
        self.hook.pageFetched(msg := f"获取了{len(feeds)}条说说, {len(new)}条最新")
        logger.info(msg)
        return len(new)

    def postProcess(self, feed: Parser):
        ned = noexcept({
            BaseException: lambda _: logger.
            warning(f'Expt in {process.__name__}.', exc_info=True)
        })

        @ned
        def complete(i: Parser):
            if not i.isCut(): return
            html = self.qzone.getCompleteFeed(i.feedData)
            if html:
                i.html = html
            else:
                logger.warning(f'feed {i.feedkey}: 获取完整说说失败')

        @ned
        def album(i: Parser):
            if i.hasAlbum():
                i.parseImage(lambda d, n: self.qzone.photoList(d, i.uin, n))

        for process in [complete, album]:
            process(feed)
        return feed

    def _fetchNewFeeds(self, *, no_pred: int = False, ignore_exist=False):
        """inner fetch new feeds

        Raises:
            `HTTPError`: as it is
            `QzoneError`: if unkown qzone code returned
        """
        pred_new = self.qzone.checkUpdate()
        if no_pred or ignore_exist:
            page = no_pred if isinstance(no_pred, int) and no_pred > 0 else 1000
        else:
            if pred_new == 0: return 0
            page = 1 + ceil((pred_new - 5) / 10)

        if page <= self.executor._max_workers:
            new_iter = self.executor.map(
                lambda i: self.getNewFeeds(i + 1, ignore_exist), range(page)
            )
        else:
            new_iter = takewhile(
                bool, (self.getNewFeeds(i + 1, ignore_exist) for i in range(page))
            )
        s = sum(new_iter)
        if s < pred_new:
            logger.warning(f'Expect to get {pred_new} new feeds, but actually {s}')
        return s

    def fetchNewFeeds(self, *, no_pred=False, ignore_exist=False):
        """fetch all new feeds.

        Args:
            `no_pred`: do not predict new feeds amount
            `ignore_exist` (bool, optional): Force reload to ignore any feed already in storage. Defaults to False.

        Raises:
            `UserBreak`

        Returns:
            `int`: new feeds amount
        """
        try:
            return self._fetchNewFeeds(no_pred=no_pred, ignore_exist=ignore_exist)
        except KeyboardInterrupt:
            raise UserBreak
        except LoginError as e:
            self.hook.loginFailed(e.args[0])
            return 0
        except (HTTPError, QzoneError) as e:
            exc_info = False
        except Exception as e:
            exc_info = True

        logger.error(
            f"{type(e)} when fetching pages: " + str(e),
            exc_info=exc_info,
        )
        return 0

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
