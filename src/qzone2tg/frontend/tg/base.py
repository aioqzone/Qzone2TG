import logging
from datetime import time as Time
from functools import wraps
from typing import Callable

from pytz import timezone
from qzone2tg.qzone.exceptions import UserBreak
from qzone2tg.qzone.feed import QzCachedScraper
from qzone2tg.utils.decorator import Locked, atomic
from requests.exceptions import HTTPError
from telegram.ext import Updater

from .ui import TgExtracter, TgUI, retry_once

TIME_ZONE = timezone('Asia/Shanghai')
logger = logging.getLogger(__name__)


class RefreshBot:
    reload_on_start = False

    def __init__(
        self,
        feedmgr: QzCachedScraper,
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
        self._register_decorators()
        self.ui.register_sendfeed_callback(self.sendFeedCallback)

        self.update.job_queue.run_daily(
            lambda c: self.feedmgr.cleanFeed(),
            Time(tzinfo=TIME_ZONE),
            name='clean feed'
        )

    def _register_decorators(self):
        self.feedmgr.db.setPluginData = atomic(self.feedmgr.db.setPluginData)
        for i in [self.onSend, self.onFetch, self.sendFeedCallback]:
            setattr(self, i.__name__, self._runAsync(i))
        for i, n in {self.onSend: 'sending', self.onFetch: 'fetching'}.items():
            setattr(self, i.__name__, self._notifyLock(n)(i))

    def _runAsync(self, func: Callable):
        @wraps(func)
        def asyncWrapper(*args, **kwargs):
            return self.update.dispatcher.run_async(func, *args, **kwargs)

        return asyncWrapper

    def _notifyLock(self, name=None):
        def lockDecorator(func: Callable):
            noti_name = name or func.__name__
            return Locked(
                lambda: logger.info(f"{func.__name__}: new {noti_name} excluded.") or \
                self.ui.bot.sendMessage(f"Sorry. But the bot is {noti_name} already."),
            )(func)

        return lockDecorator

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

    def idle(self):
        self.onFetch(reload=self.reload_on_start)
        self.register_period_refresh()
        self.update.idle()

    def run(self):
        self.idle()

    def onSend(self, reload=False, period=False):
        err = 0
        new = self.feedmgr.db.getFeed(
            cond_sql='' if reload else 'is_sent IS NULL OR is_sent=0',
            plugin_name='tg',
            order=True,
        )
        if new == False: return self.ui.fetchError('数据库出错, 请检查数据库')

        for i in new:
            self.sendFeedCallback(i)

        self.ui.fetchEnd(len(new) - err, err, period)

    def onFetch(self, reload: bool, period=False):
        cmd = "force-refresh" if reload else "refresh"
        if period:
            logger.debug(f"start period {cmd}")
        else:
            logger.info(f"{self.accept_id}: start {cmd}")

        try:
            self.feedmgr.fetchNewFeeds(no_pred=not period, ignore_exist=reload)
        except TimeoutError:
            self.ui.fetchError("爬取超时, 刷新或许可以)")
            return
        except HTTPError:
            self.ui.fetchError('爬取出错, 刷新或许可以)')
            return
        except UserBreak:
            self.ui.QrCanceled()
            return
        except Exception:
            logger.error("Uncaught error when fetch", exc_info=True)
            self.ui.fetchError()
            return

        if not period:
            job = self._refresh_job.job
            job.reschedule(job.trigger)

    def sendFeedCallback(self, feed):
        feed = TgExtracter(feed, self.uin)
        if feed.isBlocked: return
        try:
            msgs = retry_once(lambda exc: f"feed {feed.feed}: {exc}")(
                self.ui.contentReady
            )(
                *feed.content(),
                feed.likeButton() if hasattr(self, 'like') else None,
            )
            self.feedmgr.db.setPluginData('tg', feed.feed.fid, is_sent=1)
            feed.imageFuture and feed.imageFuture.add_done_callback(  # BUG: feeds here is read from disk, and has no attr:img_future
                lambda f: self.ui.mediaUpdate(msgs, f.result()) # so that the callback cannot be registered all the time
            )
        except BaseException as e:
            logger.error(f"{feed.feed}: {str(e)}", exc_info=True)
