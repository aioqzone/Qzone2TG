import logging
from datetime import time as Time
from functools import wraps
from typing import Any, Callable

from pytz import timezone
from qzone.exceptions import UserBreak
from qzone.feed import QZCachedScraper
from requests.exceptions import HTTPError
from telegram.ext import Updater

from utils.decorator import LockedMethod

from .ui import TgExtracter, TgUI, retry_once

TIME_ZONE = timezone('Asia/Shanghai')
logger = logging.getLogger(__name__)


class _DecHelper:
    @staticmethod
    def asyncRun(func: Callable):
        @wraps(func)
        def asyncWrapper(self, *args, **kwargs):
            self.update.job_queue.run_custom(
                lambda c: func(self, *args, **kwargs), {}, name=func.__name__
            )

        return asyncWrapper

    @staticmethod
    def notifyLock(name=None):
        def lockDecorator(func: Callable):
            noti_name = name or func.__name__
            return LockedMethod(
                lambda self: logger.info(f"{func.__name__}: new {noti_name} excluded.") or \
                self.ui.bot.sendMessage(f"Sorry. But the bot is {noti_name} already.")
            )(func)

        return lockDecorator


class RefreshBot(_DecHelper):
    flood_limit = 30

    def __init__(
        self,
        feedmgr: QZCachedScraper,
        token: str,
        accept_id: int,
        uin: int,
        *,
        times_per_second: int = None,
        disable_notification: bool = False,
        proxy: dict = None,
    ):
        self.accept_id = int(accept_id)
        self.feedmgr = feedmgr
        self._token = token
        self.uin = int(uin)

        self.update = Updater(token, use_context=True, request_kwargs=proxy)
        self.ui = TgUI(
            self.update.bot,
            accept_id,
            times_per_second=times_per_second,
            disable_notification=disable_notification,
        )
        self.silentApscheduler()

        self.update.job_queue.run_daily(
            lambda c: self.feedmgr.cleanFeed(),
            Time(tzinfo=TIME_ZONE),
            name='clean feed'
        )

    def __del__(self):
        self.update.stop()

    def register_period_refresh(self):
        self._refresh_job = self.update.job_queue.run_repeating(
            lambda c: self.onFetch(reload=False, period=True),
            300,
            name='period_refresh'
        )
        logger.info('periodically refresh registered.')

    def silentApscheduler(self):
        if logger.level >= logging.WARN: return
        logging.getLogger("apscheduler.scheduler").setLevel(logging.WARN)
        logging.getLogger("apscheduler.executors.default").setLevel(logging.WARN)

    def run(self):
        self.register_period_refresh()
        logger.info("start refreshing")
        self.update.idle()

    @_DecHelper.asyncRun
    @_DecHelper.notifyLock('sending')
    def onSend(self, reload=False, period=False):
        err = 0
        new = self.feedmgr.db.getFeed(
            cond_sql='' if reload else 'is_sent IS NULL OR is_sent=0',
            plugin_name='tg',
            order=True,
        )
        if new == False: return self.ui.fetchError('数据库出错, 请检查数据库')

        for i in new:
            try:
                i = TgExtracter(i, self.uin)
                if i.isBlocked: continue
                send_w_retry = retry_once(
                    self.ui.contentReady, lambda exc: f"feed {i.feed}: {exc}"
                )
                send_w_retry(
                    *i.content(),
                    i.likeButton() if hasattr(self, 'like') else None,
                )
                self.feedmgr.db.setPluginData('tg', i.feed.fid, is_sent=1)
            except Exception as e:
                logger.error(f"{i.feed}: {str(e)}", exc_info=True)
                err += 1
                continue
        self.ui.fetchEnd(len(new) - err, err, period)

    @_DecHelper.asyncRun
    @_DecHelper.notifyLock('fetching')
    def onFetch(self, reload: bool, period=False):
        cmd = "force-refresh" if reload else "refresh"
        if period:
            logger.debug(f"start period {cmd}")
        else:
            logger.info(f"{self.accept_id}: start {cmd}")

        try:
            r = self.feedmgr.fetchNewFeeds(no_pred=not period, ignore_exist=reload)
        except TimeoutError:
            self.ui.fetchError("爬取超时, 刷新或许可以)")
            return
        except HTTPError:
            self.ui.fetchError('爬取出错, 刷新或许可以)')
            return
        except UserBreak:
            self.ui.QrCanceled()
            return
        except Exception as e:
            logger.error(str(e), exc_info=True)
            self.ui.fetchError()
            return

        if r: self.onSend(reload=reload, period=period)
        if not period:
            job = self._refresh_job.job
            job.reschedule(job.trigger)
