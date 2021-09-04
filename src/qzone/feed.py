import logging

from middleware.storage import FeedBase, day_stamp
from middleware.uihook import NullUI
from requests.exceptions import HTTPError

from utils.decorator import Retry

from . import QzoneScraper
from .exceptions import LoginError, UserBreak
from .parser import QZFeedParser as Parser

logger = logging.getLogger(__name__)
PAGE_LIMIT = 1000


class QZCachedScraper:
    new_limit = 30         # not implement
    ui = NullUI()

    def __init__(self, qzone: QzoneScraper, db: FeedBase):
        self.qzone = qzone
        self.db = db

    def register_ui_hook(self, ui: NullUI):
        self.ui = ui

    def cleanFeed(self):
        self.db.cleanFeed()

    def getFeedsInPage(self, pagenum: int, reload=False):
        """get compelte feeds from qzone and save them to database

        Args:
            `pagenum` (int): page #
            `reload` (bool, optional): whether to ignore existing feed. Defaults to False.

        Return:
            bool: if success

        Raises:
            UserBreak: see qzone.updateStatus
        """        
        def bomb(e):            raise e    # yapf: disable

        retry403 = Retry({
            HTTPError: lambda e, i: e.response.status_code != 403 and bomb(e)
        })
        fetch_w_retry = retry403(self.qzone.fetchPage)
        try:
            feeds = fetch_w_retry(pagenum)
        except HTTPError as e:
            logger.error(
                f"HTTPError when getting page {pagenum}. Code: {e.response.status_code}"
            )
            return False
        except KeyboardInterrupt:
            raise UserBreak
        except LoginError as e:
            logger.error(f"LoginError: " + e.msg)
            return False
        except Exception as e:
            logger.error(
                f"{type(e)} when getting page {pagenum}. " + str(e), exc_info=True
            )
            return False

        if feeds is None: return False
        assert isinstance(feeds, list)

        limit = day_stamp() - self.db.keepdays
        new = [
            p for i in feeds
            if ((p := Parser(i)) and reload or p.fid not in self.db.feed)
            and day_stamp(p.abstime) > limit
        ]
        self.ui.pageFetched(msg := f"获取了{len(feeds)}条说说, {len(new)}条最新")
        logger.info(msg)
        if not new: return False

        for i in new:
            if not i.isCut(): continue
            html = self.qzone.getCompleteFeed(i.parseFeedData())
            if html:
                i.updateHTML(html)
            else:
                logger.warning(f'feed {i.hash}: 获取完整说说失败')

        self.db.saveFeeds(new)
        return True

    def fetchNewFeeds(self, reload=False):
        flag = False
        for i in range(PAGE_LIMIT):
            tmp = self.getFeedsInPage(i + 1, reload)
            if not tmp: break
            flag = True
        return flag

    def like(self, likedata: dict):
        return self.qzone.doLike(likedata)

    def likeAFile(self, fid: str):
        r = self.db.feed[fid] or self.db.archive[fid]
        if not r: raise FileNotFoundError
        return self.like(Parser(r).getLikeId())
