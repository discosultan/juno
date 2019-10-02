from __future__ import annotations

import logging
from typing import AsyncIterable, List, Optional

import aiohttp
import backoff

from juno import Candle
from juno.asyncio import list_async
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.storages import Storage
from juno.time import strfinterval, strfspan, time_ms
from juno.utils import generate_missing_spans, merge_adjacent_spans

_log = logging.getLogger(__name__)


class Chandler:
    def __init__(self, storage: Storage, exchanges: List[Exchange]) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def stream_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int, closed: bool = True
    ) -> AsyncIterable[Candle]:
        """Tries to stream candles for the specified range from local storage. If candles don't
        exist, streams them from an exchange and stores to local storage."""
        storage_key = (exchange, symbol, interval)
        candle_msg = f'{symbol} {strfinterval(interval)} candles'

        _log.info(f'checking for existing {candle_msg} in local storage')
        existing_spans = await list_async(
            self._storage.stream_candle_spans(storage_key, start, end)
        )
        merged_existing_spans = list(merge_adjacent_spans(existing_spans))
        missing_spans = list(generate_missing_spans(start, end, merged_existing_spans))

        spans = ([(a, b, True) for a, b in merged_existing_spans] + [(a, b, False)
                                                                     for a, b in missing_spans])
        spans.sort(key=lambda s: s[0])

        for span_start, span_end, exist_locally in spans:
            period_msg = f'{strfspan(span_start, span_end)}'
            if exist_locally:
                _log.info(f'local {candle_msg} exist between {period_msg}')
                async for candle in self._storage.stream_candles(
                    storage_key, span_start, span_end
                ):
                    if not closed or candle.closed:
                        yield candle
            else:
                _log.info(f'missing {candle_msg} between {period_msg}')
                async for candle in self._stream_and_store_exchange_candles(
                    exchange, symbol, interval, span_start, span_end
                ):
                    if not closed or candle.closed:
                        yield candle

    @backoff.on_exception(
        backoff.expo, (aiohttp.ClientConnectionError, aiohttp.ClientResponseError), max_tries=3
    )
    async def _stream_and_store_exchange_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        BATCH_SIZE = 1000
        batch = []
        batch_start = start

        try:
            async for candle in self._stream_exchange_candles(
                exchange=exchange, symbol=symbol, interval=interval, start=start, end=end
            ):
                if candle.closed:
                    batch.append(candle)
                    if len(batch) == BATCH_SIZE:
                        batch_end = batch[-1].time + interval
                        await self._storage.store_candles_and_span((exchange, symbol, interval),
                                                                   batch, batch_start, batch_end)
                        batch_start = batch_end
                        del batch[:]
                yield candle
        finally:
            if len(batch) > 0:
                batch_end = batch[-1].time + interval
                await self._storage.store_candles_and_span((exchange, symbol, interval), batch,
                                                           batch_start, batch_end)

    async def _stream_exchange_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        exchange_instance = self._exchanges[exchange]
        current = floor_multiple(time_ms(), interval)

        async def inner(future_stream: Optional[AsyncIterable[Candle]]) -> AsyncIterable[Candle]:
            if start < current:
                async for candle in exchange_instance.stream_historical_candles(
                    symbol, interval, start, min(end, current)
                ):
                    yield candle
            if future_stream:
                async for candle in future_stream:
                    yield candle

                    if candle.time >= end - interval and candle.closed:
                        break

        if end > current:
            async with exchange_instance.connect_stream_future_candles(
                symbol, interval
            ) as future_stream:
                async for candle in inner(future_stream):
                    yield candle
        else:
            async for candle in inner(None):
                yield candle
