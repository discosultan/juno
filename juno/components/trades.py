from __future__ import annotations

import logging
from typing import AsyncIterable, List, Optional

import backoff

from juno import Trade
from juno.asyncio import list_async
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import strfspan, time_ms
from juno.utils import generate_missing_spans, merge_adjacent_spans

_log = logging.getLogger(__name__)


class Trades:
    def __init__(self, storage: Storage, exchanges: List[Exchange]) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def stream_trades(
        self, exchange: str, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        """Tries to stream trades for the specified range from local storage. If trades don't
        exist, streams them from an exchange and stores to local storage."""
        storage_key = (exchange, symbol)
        trade_msg = f'{symbol} trades'

        _log.info(f'checking for existing {trade_msg} in local storage')
        existing_spans = await list_async(
            self._storage.stream_time_series_spans(storage_key, Trade, start, end)
        )
        merged_existing_spans = list(merge_adjacent_spans(existing_spans))
        missing_spans = list(generate_missing_spans(start, end, merged_existing_spans))

        spans = ([(a, b, True) for a, b in merged_existing_spans] + [(a, b, False)
                                                                     for a, b in missing_spans])
        spans.sort(key=lambda s: s[0])

        for span_start, span_end, exist_locally in spans:
            period_msg = f'{strfspan(span_start, span_end)}'
            if exist_locally:
                _log.info(f'local {trade_msg} exist between {period_msg}')
                async for trade in self._storage.stream_time_series(
                    storage_key, Trade, span_start, span_end
                ):
                    yield trade
            else:
                _log.info(f'missing {trade_msg} between {period_msg}')
                async for candle in self._stream_and_store_exchange_trades(
                    exchange, symbol, span_start, span_end
                ):
                    yield trade

    @backoff.on_exception(backoff.expo, (Exception, ), max_tries=3)
    async def _stream_and_store_exchange_trades(
        self, exchange: str, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        BATCH_SIZE = 1000
        batch = []
        batch_start = start

        try:
            async for trade in self._stream_exchange_trades(
                exchange=exchange, symbol=symbol, start=start, end=end
            ):
                batch.append(trade)
                if len(batch) == BATCH_SIZE:
                    batch_end = batch[-1].time + 1
                    await self._storage.store_time_series_and_span(
                        (exchange, symbol), Trade, batch, batch_start, batch_end
                    )
                    batch_start = batch_end
                    del batch[:]
                yield trade
        finally:
            if len(batch) > 0:
                batch_end = batch[-1].time + 1
                await self._storage.store_time_series_and_span(
                    (exchange, symbol), Trade, batch, batch_start, batch_end
                )

    async def _stream_exchange_trades(
        self, exchange: str, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        exchange_instance = self._exchanges[exchange]
        current = time_ms()

        async def inner(future_stream: Optional[AsyncIterable[Trade]]) -> AsyncIterable[Trade]:
            if start < current:
                async for trade in exchange_instance.stream_historical_trades(
                    symbol, start, min(end, current)
                ):
                    yield trade
            if future_stream:
                async for trade in future_stream:
                    yield trade

                    if trade.time >= end:
                        break

        if end > current:
            async with exchange_instance.connect_stream_trades(symbol) as future_stream:
                async for trade in inner(future_stream):
                    yield trade
        else:
            async for trade in inner(None):
                yield trade
