from typing import Callable

from juno.asyncio import list_async
from juno.math import ceil_multiple, floor_multiple
from juno.storages import Storage
from juno.time import time_ms

from .chandler import Chandler


class Historian:
    def __init__(
        self,
        chandler: Chandler,
        storage: Storage,
        get_time_ms: Callable[[], int] = time_ms,
        earliest_exchange_start: int = 1293840000000  # 2011-01-01
    ):
        self._chandler = chandler
        self._storage = storage
        self._get_time_ms = get_time_ms
        self._earliest_exchange_start = earliest_exchange_start

    async def find_first_candle_time(self, exchange: str, symbol: str, interval: int) -> int:
        key = (exchange, symbol, interval, 'first_candle')
        val, _ = await self._storage.get(key, int)
        if not val:
            val = await self._find_first_candle_time(exchange, symbol, interval)
            await self._storage.set(key, int, val)
        return val

    async def _find_first_candle_time(self, exchange: str, symbol: str, interval: int) -> int:
        # TODO: Does not handle missing candles, hence, may yield incorrect results!
        # We try to find a first candle by performing a binary search.
        start = ceil_multiple(self._earliest_exchange_start, interval)
        end = floor_multiple(self._get_time_ms(), interval)
        final_end = end  # We need this to not go into the future. We will mutate `end`.
        while True:
            mid = start + floor_multiple(((end - start) // 2), interval)
            from_ = mid
            to = min(from_ + 2 * interval, final_end)
            candles = await list_async(self._chandler.stream_candles(
                exchange, symbol, interval, from_, to
            ))
            if len(candles) == 0:
                start = mid + interval
            elif (
                len(candles) == 1
                and to - from_ > interval  # Must not be last candle.
            ):
                return candles[0].time
            else:
                end = mid

            if start >= end:
                break

        raise ValueError('First candle not found.')
