import logging
import queue
import threading
from concurrent.futures import Future
from time import sleep
from typing import Any, Callable, Generic, Tuple, TypeVar

from ..exceptions import QzoneError

T = TypeVar('T')

__all__ = ['AlbumQue', 'asqueue']
logger = logging.getLogger(__name__)


class AlbumQue(threading.Thread, Generic[T]):
    """
    Since Qzone album service is always slow to response, this module 
    is to manage a queue to arrange album requests.

    The requests will be sent within an AIMD pattern, 
    and the result will be passed through future and callback.
    """
    def __init__(self, request: Callable[[T], list]) -> None:
        super().__init__(name=request.__name__)
        self.que = queue.Queue(-1)
        self._stop = False
        self.func = request

    def run(self) -> None:
        lps: int = 0
        while not self._stop:
            future, a = self.que.get(block=True)
            try:
                r = self.func(*a)
                lps = int(lps // 2)
                future.set_result(r)
                logger.debug(
                    f"Album queue finished a request. Lapse={lps}, pending={self.pending}"
                )
            except QzoneError as e:
                if e.code != -10001: future.set_exception(e)
                lps += 1
                self.que.put((future, a))
                logger.debug(
                    f"Album queue roll back a request. Lapse={lps}, pending={self.pending}"
                )
                sleep(lps)
            except BaseException as e:
                future.set_exception(e)
            finally:
                self.que.task_done()

    @property
    def pending(self):
        """get unfinished_tasks"""
        return self.que.unfinished_tasks

    def add(self,
            args: Tuple[T],
            cb: Callable[[Future[list]], Any] = None) -> Future[list]:
        """add a task

        Args:
            args (Tuple[T]): args for calling func
            cb (Callable[[Future[list]], Any], optional): callback. Defaults to None.

        Returns:
            Future[list]: future. get result with `future.result()`.
        """
        future = Future()
        if cb: future.add_done_callback(cb)
        self.que.put((future, args), block=True)
        return future

    def __call__(self, *args):
        return self.add(args)

    def stop(self):
        """thread will stop before next awaken (next calling func)"""
        self._stop = True


__doc__ = AlbumQue.__doc__
asqueue = AlbumQue
