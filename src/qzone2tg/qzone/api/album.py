import logging
import queue
import threading
from concurrent.futures import Future
from time import sleep
from typing import Any, Callable, Generic, Tuple, TypeVar

from ..exceptions import QzoneError

T = TypeVar('T')

__all__ = ['AlbumQue']
logger = logging.getLogger(__name__)


class AlbumTask:
    __slots__ = ('func', 'args', 'kwds', 'run_times', 'future')

    def __init__(self, func: Callable, *args, **kwds) -> None:
        self.func = func
        self.args = args
        self.kwds = kwds

        self.run_times: int = 0
        self.future = Future()


class AlbumQue(threading.Thread, Generic[T]):
    """
    Since Qzone album service is always slow to response, this module
    is to manage a queue to arrange album requests.

    The requests will be sent within an AIMD manner,
    and the result will be passed through future and callback.
    """
    def __init__(self, request: Callable[[T], list], max_retry: int = 12) -> None:
        assert callable(request)
        assert max_retry > 0
        super().__init__(name=request.__name__, daemon=True)
        self.que = queue.Queue(-1)
        self._stop = False
        self.func = request
        self.max_retry = max_retry

    def run(self) -> None:
        lps: int = 0
        while not self._stop:
            task: AlbumTask = self.que.get(block=True)
            try:
                r = self.func(*task.args)
                lps = int(lps // 2)
                logger.debug(
                    "Album queue finished a request. "
                    f"Lapse={lps}, pending={self.pending}"
                )
                task.future.set_result(r)
            except QzoneError as e:
                if e.code != -10001: task.future.set_exception(e)
                task.run_times += 1
                lps += 1
                logger.debug(
                    f"Album queue roll back a request. {e}"
                    f"Lapse={lps}, pending={self.pending}"
                )
                for _ in range(lps):
                    sleep(1)
                    if self._stop: return
                if task.run_times > self.max_retry:
                    task.future.set_exception(TimeoutError)
                    logger.warning('Album queue give up a request.')
                else:
                    self.que.put(task)
            except BaseException as e:
                task.future.set_exception(e)
            finally:
                self.que.task_done()

    @property
    def pending(self):
        """get unfinished_tasks"""
        return self.que.unfinished_tasks

    def add(self, args: Tuple[T], cb: Callable[[Future[list]], Any] = None) -> Future[list]:
        """add a task

        Args:
            args (Tuple[T]): args for calling func
            cb (Callable[[Future[list]], Any], optional): callback. Defaults to None.

        Returns:
            Future[list]: future. get result with `future.result()`.
        """
        task = AlbumTask(self.func, *args)
        if cb: task.future.add_done_callback(cb)
        self.que.put(task, block=True)
        return task.future

    def __call__(self, *args):
        return self.add(args=args)

    def stop(self):
        """thread will stop before next awaken (next calling func)"""
        self._stop = True

    def start(self) -> None:
        logger.info('Album queue starting')
        return super().start()
