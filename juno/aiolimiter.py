import asyncio
import logging

import aiolimiter

_log = logging.getLogger(__name__)


class AsyncLimiter(aiolimiter.AsyncLimiter):
    # Overrides the original implementation by adding logging when rate limiting.
    # https://github.com/mjpieters/aiolimiter/blob/master/src/aiolimiter/leakybucket.py
    async def acquire(self, amount: float = 1) -> None:
        if amount > self.max_rate:
            raise ValueError("Can't acquire more than the maximum capacity")

        loop = asyncio.get_event_loop()
        task = asyncio.current_task(loop)
        assert task is not None
        while not self.has_capacity(amount):
            waiting_time = 1 / self._rate_per_sec * amount
            _log.info(
                f"rate limiter {self.max_rate}/{self.time_period} reached; waiting up to "
                f"{waiting_time}s before retrying"
            )
            fut = loop.create_future()
            self._waiters[task] = fut
            try:
                await asyncio.wait_for(asyncio.shield(fut), waiting_time)
            except asyncio.TimeoutError:
                pass
            fut.cancel()
        self._waiters.pop(task, None)

        self._level += amount
