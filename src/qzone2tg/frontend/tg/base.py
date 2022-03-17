import logging
from bisect import bisect_left
from concurrent.futures import Future
from datetime import time as Time
from functools import wraps
from typing import Callable

import telegram
from pytz import timezone
from qqqr.exception import UserBreak
from qzone2tg.qzone.feed import QzCachedScraper
from qzone2tg.utils.decorator import Locked, atomic
from requests.exceptions import HTTPError
from telegram.error import BadRequest, TimedOut
from telegram.ext import Defaults, Updater

from .ui import TgExtracter, TgUI

TIME_ZONE = timezone('Asia/Shanghai')
logger = logging.getLogger(__name__)


class SendTransaction():
    def __init__(self) -> None:
        self.q = []
        self.clear()

    def insert(self, feed: TgExtracter):
        if not self.q or self.q[-1].feed.abstime < feed.feed.abstime:
            # since q is always sorted, bisect will fall in the worst O(n) situation.
            # check the last and quick skip bisect will cover most cases.
            x = len(self.q)
            self.q.append(feed)
        else:
            x = bisect_left([i.feed.abstime for i in self.q], feed.feed.abstime)
            self.q.insert(x, feed)
        return x

    def clear(self):
        self.is_period = False
        self.skip = 0
        self.err = 0
        self.q.clear()

    def __iter__(self):
        return iter(self.q)

    def __len__(self):
        return len(self.q)


class TgHook(TgUI):
    def __init__(self, bot, chat_id: int, like: bool, **kwds) -> None:
        self.stack = SendTransaction()
        self.like = like
        super().__init__(bot, chat_id, **kwds)

    def register_sent_callback(self, cb: Callable):
        self.sent_callback = cb

    def allFetchEnd(self, sum: int):
        logger.info(f'Fetched {sum}, sending {len(self.stack)}')
        if len(self.stack) + self.stack.skip + self.stack.err != sum:
            logger.warning('Some feeds may be omitted.')

        for i, feed in enumerate(self.stack):
            try:
                self._sendExtracter(feed)
                logger.debug(f'message sent {i + 1}/{len(self.stack)}')
            except:
                logger.error('FATAL: exception out of catch!!!')
                self.stack.err += 1

        err, silent = self.stack.err, self.stack.is_period
        self.stack.clear()
        logger.debug('TgHook stack cleared')
        self._fetchEnd(sum - err, err, silent=silent)

    def feedFetched(self, feed):
        feed = TgExtracter(feed)
        if feed.isBlocked:
            self.stack.skip += 1
            return
        try:
            feed.prepare()
        except:
            self.stack.err += 1
        else:
            self.stack.insert(feed)

    def __contentReady(self, feed: TgExtracter):
        msg, media = feed.content()
        reply_markup = None
        if self.like: reply_markup = feed.likeButton()
        if media:
            return self.bot.sendMedia(msg, media, reply_markup)
        else:
            return self.bot.sendMessage(msg, reply_markup)

    def _contentReady(self, feed: TgExtracter):
        for i in range(2):
            if i < 1:
                try:
                    return self.__contentReady(feed)
                except TimedOut as e:
                    logger.warning(e.message)
                except BadRequest as e:
                    logger.error(f'BadRequest. Args: {feed.content()}')
                except BaseException as e:
                    logger.error(f"feed {feed.feed}: {e}", exc_info=True)
            else:
                try:
                    return self.__contentReady(feed)
                except:
                    logger.error("Max retry exceed.", exc_info=True)
        return []

    def _sendExtracter(self, feed: TgExtracter):
        msgs = self._contentReady(feed)
        if not msgs: return
        self.sent_callback(feed.feed)
        if feed.imageFuture:

            def update_media_callback(future: Future):
                try:
                    media = future.result()
                except:    # TODO: QzoneError; TimeoutError
                    return
                try:
                    self.updateMedia(msgs, media)
                except TimedOut:
                    logger.warning('Edit media timeout repeatedly. Skipped.')
                    return
                except:
                    logger.error(f"{feed.feed}: error when editing media", exc_info=True)
                    return

            feed.imageFuture.add_done_callback(update_media_callback)


class RefreshBot:
    reload_on_start = False

    def __init__(
        self,
        feedmgr: QzCachedScraper,
        token: str,
        accept_id: int,
        *,
        times_per_second: int = None,
        disable_notification: bool = False,
        network: dict = None,
    ):
        self.accept_id = int(accept_id)
        self.feedmgr = feedmgr
        self._token = token

        defaults = Defaults(
            parse_mode=telegram.ParseMode.HTML,
            disable_notification=disable_notification,
            tzinfo=TIME_ZONE
        )
        self.update = Updater(token, use_context=True, request_kwargs=network, defaults=defaults)
        self.ui = TgHook(
            self.update.bot,
            accept_id,
            like=hasattr(self, 'like'),
            times_per_second=times_per_second,
        )
        self.silentApscheduler()
        self._register_decorators()
        self.ui.register_sent_callback(
            lambda feed: self.feedmgr.db.setPluginData('tg', feed.fid, is_sent=1)
        )

        self.update.job_queue.run_daily(
            lambda c: self.feedmgr.cleanFeed(), Time(tzinfo=TIME_ZONE), name='clean feed'
        )

    @staticmethod
    def addBlockUin(uin: int):
        TgExtracter.blocked.add(uin)

    def _register_decorators(self):
        self.feedmgr.db.setPluginData = atomic(self.feedmgr.db.setPluginData)
        for i in [self.onSend, self.onFetch]:
            setattr(self, i.__name__, self._runAsync(i))
        for i in [self.ui.feedFetched, self.ui.allFetchEnd]:
            setattr(self.ui, i.__name__, self._runAsync(i))
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
            lambda c: RefreshBot.onFetch(self, reload=False, period=True),
            300,
            name='period_refresh'
        )
        logger.info('periodically refresh registered.')

    def silentApscheduler(self):
        if logger.level >= logging.WARN or logger.level == logging.DEBUG: return
        logging.getLogger("apscheduler.scheduler").setLevel(logging.WARN)
        logging.getLogger("apscheduler.executors.default").setLevel(logging.WARN)

    def run(self):
        self.register_period_refresh()
        RefreshBot.onFetch(self, reload=self.reload_on_start)
        self.update.user_sig_handler = lambda signum, frame: self.feedmgr.stop()
        self.update.idle()

    def onSend(self, reload=False):
        new = self.feedmgr.db.getFeed(
            cond_sql='' if reload else 'is_sent IS NULL OR is_sent=0',
            plugin_name='tg',
            order=True,
        )
        for i in new:
            self.ui.feedFetched(i)
        self.ui.stack.is_period = False
        self.ui.allFetchEnd(len(new))

    def onFetch(self, reload: bool, period=False):
        cmd = "force-refresh" if reload else "refresh"
        if period:
            logger.debug(f"start period {cmd}")
        else:
            logger.info(f"{self.accept_id}: start {cmd}")

        self.ui.stack.is_period = period
        try:
            self.feedmgr.fetchNewFeeds(no_pred=not period, ignore_exist=reload)
        except TimeoutError:
            self.ui.fetchError("爬取超时, 刷新或许可以)")
            return
        except HTTPError:
            self.ui.fetchError('爬取出错, 刷新或许可以)')
            return
        except UserBreak:
            return
        except BaseException:
            logger.error("Uncaught error when fetch", exc_info=True)
            self.ui.fetchError()
            return

        if not period:
            job = self._refresh_job.job
            job.reschedule(job.trigger)