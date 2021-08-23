import enum
import logging

from middleware.storage import FeedBase, day_stamp
from middleware.uihook import NullUI
from requests.exceptions import HTTPError

from . import QzoneScraper
from .exceptions import LoginError
from .parser import QZFeedParser as Parser

logger = logging.getLogger(__name__)
PAGE_LIMIT = 1000


class QZCachedScraper:
    new_limit = 30         # not implement

    def __init__(self, qzone: QzoneScraper, keepdays=3, archivedays=180, plugins=None):
        self.qzone = qzone
        self.db = FeedBase(f"data/{qzone.uin}.db", keepdays, archivedays, plugins)

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
            return False
        except Exception:
            logger.error(
                f'Error fetch page {pagenum}{", force reload" if reload else ""}, retry remains={retry}',
                exc_info=True
            )

        limit = day_stamp() - self.db.keepdays
        new = [
            p for i in feeds
            if (p := Parser(i)).fid not in self.db.feed and day_stamp(p.abstime) > limit
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
            reload = False
        return flag

    def like(self, likedata: dict):
        return self.qzone.doLike(likedata)

    def likeAFile(self, fid: str) -> bool:
        r = self.db.getFeed(f'fid={fid}')
        if r:
            r = r[0].getLikeId()
        else:
            r = self.db.getArchive(fid)
        return r and self.like(r)
