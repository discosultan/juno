from juno.storages import Storage
from juno.time import time_ms

from .chandler import Chandler

_EARLIEST_EXCHANGE_START = 1293840000000  # 2011-01-01


class Historian:
    def __init__(self, chandler: Chandler, storage: Storage):
        self.chandler = chandler
        self.storage = storage

    async def find_first_candle_time(self, exchange: str, symbol: str, interval: int) -> int:
        key = (exchange, symbol, interval, 'first_candle')
        val, _ = await self.storage.get(key, int)
        if not val:
            val = await self._find_first_candle_time(exchange, symbol)
            await self.storage.set(key, int, val)
        return val

    async def _find_first_candle_time(self, exchange: str, symbol: str, interval: int) -> int:
        # Binary search.
        start = _EARLIEST_EXCHANGE_START
        end = time_ms()
        mid = start + ((end - start) / 2)
        self.chandler.stream_candles(exchange, symbol, interval)
