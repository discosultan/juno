import logging
import sys
from typing import Callable, List

from juno import Candle
from juno.asyncio import first_async
from juno.exchanges import Exchange
from juno.math import ceil_multiple, floor_multiple
from juno.storages import Storage
from juno.time import time_ms
from juno.utils import key

from .chandler import Chandler

_log = logging.getLogger(__name__)

FIRST_CANDLE_KEY = 'first_candle'


class Historian:
    def __init__(
        self,
        chandler: Chandler,
        storage: Storage,
        exchanges: List[Exchange],
        get_time_ms: Callable[[], int] = time_ms,
        earliest_exchange_start: int = 1293840000000  # 2011-01-01
    ):
        self._chandler = chandler
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time_ms = get_time_ms
        self._earliest_exchange_start = earliest_exchange_start

    async def find_first_candle(self, exchange: str, symbol: str, interval: int) -> Candle:
        shard = key(exchange, symbol, interval)
        candle = await self._storage.get(
            shard=shard,
            key=FIRST_CANDLE_KEY,
            type_=Candle,
        )
        if not candle:
            if self._exchanges[exchange].can_stream_historical_earliest_candle:
                candle = await first_async(self._exchanges[exchange].stream_historical_candles(
                    symbol=symbol, interval=interval, start=0, end=sys.maxsize
                ))
            else:
                candle = await self._find_first_candle_by_binary_search(exchange, symbol, interval)
            await self._storage.set(
                shard=shard,
                key=FIRST_CANDLE_KEY,
                item=candle,
            )
        assert candle
        return candle

    async def _find_first_candle_by_binary_search(
        self, exchange: str, symbol: str, interval: int
    ) -> Candle:
        _log.info(
            f'{exchange} does not support streaming earliest candle; finding by binary search'
        )

        # TODO: Does not handle missing candles, hence, may yield incorrect results!
        start = ceil_multiple(self._earliest_exchange_start, interval)
        end = floor_multiple(self._get_time_ms(), interval)
        final_end = end  # We need this to not go into the future. We will mutate `end`.
        while True:
            mid = start + floor_multiple(((end - start) // 2), interval)
            from_ = mid
            to = min(from_ + 2 * interval, final_end)
            candles = await self._chandler.list_candles(exchange, symbol, interval, from_, to)
            if len(candles) == 0:
                start = mid + interval
            elif (
                len(candles) == 1
                and to - from_ > interval  # Must not be last candle.
            ):
                return candles[0]
            else:
                end = mid

            if start >= end:
                break

        raise ValueError('First candle not found')
