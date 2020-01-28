from typing import Callable, Optional

from juno.asyncio import list_async
from juno.math import ceil_multiple, floor_multiple
from juno.storages import Storage
from juno.time import time_ms

from .chandler import Chandler

_EARLIEST_EXCHANGE_START = 1293840000000  # 2011-01-01


class Historian:
    def __init__(
        self,
        chandler: Chandler,
        storage: Storage,
        get_time_ms: Optional[Callable[[], int]] = None,
        earliest_exchange_start: int = _EARLIEST_EXCHANGE_START
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
        end = floor_multiple(time_ms(), interval)
        while True:
            mid = start + floor_multiple(((end - start) // 2), interval)
            candles = await list_async(self._chandler.stream_candles(
                exchange, symbol, interval, mid, min(mid + 2 * interval, end)
            ))
            if len(candles) == 0:
                start = mid + 2 * interval
            elif len(candles) == 1:
                return candles[0].time
            else:
                end = mid

            if start >= end:
                raise ValueError('First candle not found.')
