from __future__ import annotations

import logging
import sys
from decimal import Decimal
from typing import AsyncIterable, Callable, List, Optional

import backoff

from .trades import Trades
from juno import Candle
from juno.asyncio import list_async
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.storages import Storage
from juno.time import strfinterval, strfspan, time_ms
from juno.utils import generate_missing_spans, merge_adjacent_spans

_log = logging.getLogger(__name__)


class Chandler:
    def __init__(
        self, trades: Trades, storage: Storage, exchanges: List[Exchange],
        get_time: Optional[Callable[[], int]] = None, storage_batch_size: int = 1000
    ) -> None:
        assert storage_batch_size > 0

        self._trades = trades
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time = get_time or time_ms
        self._storage_batch_size = storage_batch_size

    async def stream_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int, closed: bool = True
    ) -> AsyncIterable[Candle]:
        """Tries to stream candles for the specified range from local storage. If candles don't
        exist, streams them from an exchange and stores to local storage."""
        storage_key = (exchange, symbol, interval)
        candle_msg = f'{symbol} {strfinterval(interval)} candles'

        _log.info(f'checking for existing {candle_msg} in local storage')
        existing_spans = await list_async(
            self._storage.stream_time_series_spans(storage_key, Candle, start, end)
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
                async for candle in self._storage.stream_time_series(
                    storage_key, Candle, span_start, span_end
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

    @backoff.on_exception(backoff.expo, (Exception, ), max_tries=3)
    async def _stream_and_store_exchange_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        batch = []
        batch_start = start
        current = floor_multiple(self._get_time(), interval)

        try:
            async for candle in self._stream_exchange_candles(
                exchange=exchange, symbol=symbol, interval=interval, start=start, end=end,
                current=current
            ):
                if candle.closed:
                    batch.append(candle)
                    if len(batch) == self._storage_batch_size:
                        batch_end = _get_span_end(batch, interval)
                        await self._storage.store_time_series_and_span(
                            key=(exchange, symbol, interval),
                            type=Candle,
                            items=batch,
                            start=batch_start,
                            end=batch_end,
                        )
                        batch_start = batch_end
                        del batch[:]
                yield candle
        finally:
            if len(batch) > 0:
                await self._storage.store_time_series_and_span(
                    key=(exchange, symbol, interval),
                    type=Candle,
                    items=batch,
                    start=batch_start,
                    end=_get_span_end(batch, interval),
                )

    async def _stream_exchange_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int, current: int
    ) -> AsyncIterable[Candle]:
        exchange_instance = self._exchanges[exchange]

        async def inner(stream: Optional[AsyncIterable[Candle]]) -> AsyncIterable[Candle]:
            if start < current:  # Historical.
                historical_end = min(end, current)
                if exchange_instance.can_stream_historical_candles:
                    async for candle in exchange_instance.stream_historical_candles(
                        symbol, interval, start, historical_end
                    ):
                        yield candle
                else:
                    async for candle in self._stream_construct_candles(
                        exchange, symbol, interval, start, historical_end
                    ):
                        yield candle
            if stream:  # Future.
                async for candle in stream:
                    yield candle

                    if candle.time >= end - interval and candle.closed:
                        break

        if end > current:
            if exchange_instance.can_stream_candles:
                async with exchange_instance.connect_stream_candles(symbol, interval) as stream:
                    async for candle in inner(stream):
                        yield candle
            else:
                stream = self._stream_construct_candles(exchange, symbol, interval, current, end)
                async for candle in inner(stream):
                    yield candle
        else:
            async for candle in inner(None):
                yield candle

    async def _stream_construct_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        current = start
        next_ = current + interval
        open_ = Decimal(0)
        high = Decimal(0)
        low = Decimal(sys.maxsize)
        close = Decimal(0)
        volume = Decimal(0)
        is_first = True
        async for trade in self._trades.stream_trades(exchange, symbol, start, end):
            if trade.time >= next_:
                assert not is_first
                yield Candle(
                    time=current,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    closed=True)
                current = next_
                next_ = current + interval
                open_ = Decimal(0)
                high = Decimal(0)
                low = Decimal(sys.maxsize)
                close = Decimal(0)
                volume = Decimal(0)
                is_first = True

            if is_first:
                open_ = trade.price
                is_first = False
            high = max(high, trade.price)
            low = min(low, trade.price)
            close = trade.price
            volume += trade.size

        if not is_first:
            yield Candle(
                time=current,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                closed=True)


def _get_span_end(batch: List[Candle], interval: int) -> int:
    # We could optimize it to historically also extend the end period in case of missed candles.
    # However, the impact is negligible and not worth the complexity.
    return batch[-1].time + interval
