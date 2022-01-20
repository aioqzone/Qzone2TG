import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import takewhile
from math import ceil
from typing import Callable, Iterable, Union

from qqqr.exception import UserBreak

from ..middleware.hook import NullUI
from ..middleware.storage import FeedBase
from ..middleware.utils import day_stamp
from ..utils.decorator import atomic, noexcept
from .exceptions import LoginError
from .parser import QzJsonParser as Parser
from .api import QzoneApi

logger = logging.getLogger(__name__)
FeedProcess = Callable[[Parser], None]


class FeedDB(FeedBase):
    def getFeed(self, cond_sql: str = '', plugin_name=None, order=False):
        return [
            Parser(i)
            for i in super().getFeed(cond_sql=cond_sql, plugin_name=plugin_name, order=order)
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


class PostProcess:
    def __init__(self, max_worker=2) -> None:
        self.executor = ThreadPoolExecutor(max_worker, thread_name_prefix='feedprocess')
        self.post = []

    def register_postprocess(self, proc: FeedProcess):
        ned = noexcept({
            BaseException: lambda _: logger.warning(f'Expt in {proc.__name__}:', exc_info=True)
        })
        self.post.append(ned(proc))

    def postProcess(self, i: Parser):
        for f in self.post:
            f(i)
        return i

    def stop(self):
        self.executor.shutdown(False)


class QzFeedScraper(PostProcess):
    """Top feed API"""

    hook = NullUI()

    def _post_complete(self, i: Parser):
        if not i.isCut(): return
        if (html := self.qzone.getCompleteFeed(i.feedData)):
            i.html = html
        else:
            logger.warning(f'feed {i.feedkey}: 获取完整说说失败')

    def _post_album(self, i: Parser):
        i.setAlbumFuture(lambda d, n: self.qzone.photoList(d, i.uin, n))

    def __init__(self, qzone: QzoneApi, max_worker=None):
        super().__init__(max_worker)
        self.qzone = qzone
        self.register_postprocess(self._post_complete)
        self.register_postprocess(self._post_album)

    def stop(self):
        super().stop()
        self.qzone.stop()

    def register_ui_hook(self, hook: NullUI):
        self.hook = hook
        self.qzone.register_ui_hook(hook)

    def check_exist(self, fid: str):
        return False

    def getNewFeeds(self, pagenum: int, day_limit: int, ignore_exist=False):
        feeds = self.qzone.fetchPage(pagenum)
        if feeds is None: return []

        @noexcept({
            BaseException: lambda _: logger.error('Expt in concurrent context.', exc_info=True)
        })
        def concurrent(i: dict):
            # a coarse concurrency. need further optimization.
            feed = Parser(i)
            if day_stamp(feed.abstime) < day_limit: return
            if not ignore_exist and self.check_exist(feed.fid): return
            self.hook.feedFetched(self.postProcess(feed))
            return feed

        # To avoid any unexpected behavior, `concurrent` should be noexcept.
        logger.debug('multi-thread map for post processing')
        new = self.executor.map(concurrent, feeds)
        new = list(filter(None, new))

        self.hook.pageFetched(msg := f"获取了{len(feeds)}条说说, {len(new)}条最新")
        logger.info(msg)
        return new

    def _fetchNewFeeds(self, *, no_pred: Union[bool, int] = False, ignore_exist=False):
        """inner fetch new feeds

        Raises:
            `HTTPError`: as it is
            `QzoneError`: if unkown qzone code returned
        """
        pred_new = self.qzone.checkUpdate()
        if no_pred or ignore_exist:
            page = 1000 if isinstance(no_pred, bool) or no_pred <= 0 else no_pred
        else:
            if pred_new == 0: return 0
            page = 1 + ceil((pred_new - 5) / 10)

        if page <= self.executor._max_workers:
            logger.debug('multi-thread map for get multiple pages')
            new_iter = self.executor.map(
                lambda i: self.getNewFeeds(i + 1, ignore_exist), range(page)
            )
        else:
            new_iter = takewhile(
                bool, (self.getNewFeeds(i + 1, ignore_exist) for i in range(page))
            )
        s = sum(len(i) for i in new_iter)
        if s < pred_new:
            logger.warning(f'Expect to get {pred_new} new feeds, but actually {s}')

        self.hook.allFetchEnd(s)
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
        except Exception as e:
            logger.error(
                f"{type(e)} when fetching pages: " + str(e),
                exc_info=True,
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


class QzCachedScraper(QzFeedScraper):
    """Easy API for scraper + Database
    """
    def __init__(self, qzone: QzoneApi, db: FeedDB, max_worker=None):
        super().__init__(qzone, max_worker)
        self.db = db
        self.cleanFeed = self.db.cleanFeed
        self.cleanFeed()

    @atomic
    def check_exist(self, fid: str):
        return fid in self.db.feed

    def getNewFeeds(
        self,
        pagenum: int,
        ignore_exist=False,
    ):
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

        new = super().getNewFeeds(
            pagenum=pagenum, day_limit=day_stamp() - self.db.keepdays, ignore_exist=ignore_exist
        )
        self.db.saveFeeds(new)
        return new

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
        lid = Parser(r).getLikeId()
        if not lid: return False
        return self.like(lid)
