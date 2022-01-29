"""A message queue for sending feeds."""

import asyncio
from collections import defaultdict
import time


class _rsct:
    """We need this because telegram api limits bot message frequency per senconds.

    The limit includes (text) message, image message and gallery message. Thus all `send_message`,
    `send_photo`, `send_group_message` must be wrapped by this context derived from the same semaphore."""
    _start: float

    def __init__(self, lock: 'RelaxSemaphore', num: int = 1):
        self.lock = lock
        self.num = num
        self._slice = num / lock._max

    async def __aenter__(self):
        await self.lock.acquire(self.num)
        self._start = time.time()
        return None

    async def __aexit__(self, *exc):
        await asyncio.sleep(self._start + self._slice - time.time())
        self.lock.release(self.num)


class RelaxSemaphore(asyncio.Semaphore):
    _loop: asyncio.AbstractEventLoop

    def __init__(self, value: int = 30):
        self._max = value
        super().__init__(value)

    async def acquire(self, num: int = 1) -> bool:
        """Do NOT acquire from RelaxSemaphore directly.

        Example:

        >>> sem = RelaxSemaphore(30)
        >>> async with sem.num(5):  # always call with RelaxSemaphore.num
        >>>     send_gallery(...)
        """
        for i in range(num):
            await super().acquire()
        return True

    def release(self, num: int = 1) -> None:
        for i in range(num):
            super().release()

    def num(self, num: int = 1):
        return _rsct(self, num)
