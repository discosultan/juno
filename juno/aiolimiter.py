import logging

import aiolimiter

_log = logging.getLogger(__name__)


class AsyncLimiter(aiolimiter.AsyncLimiter):
    # Overrides the original implementation by adding logging when rate limiting.
    # https://github.com/mjpieters/aiolimiter/blob/master/src/aiolimiter/leakybucket.py
    async def acquire(self, amount: float = 1) -> None:
        if not self.has_capacity():
            timeout = 1 / self._rate_per_sec * amount
            _log.info(
                f"rate limiter {self.max_rate}/{self.time_period} reached; waiting up to "
                f"{timeout}s before retrying"
            )
        await super().acquire(amount)
