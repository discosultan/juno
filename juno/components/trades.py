from __future__ import annotations

import logging
from typing import AsyncIterable, Callable, List, Optional

import backoff

from juno import Trade
from juno.asyncio import list_async
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import strfspan, time_ms
from juno.utils import generate_missing_spans, merge_adjacent_spans

_log = logging.getLogger(__name__)


class Trades:
    def __init__(
        self,
        storage: Storage,
        exchanges: List[Exchange],
        get_time: Optional[Callable[[], int]] = None,
        storage_batch_size: int = 1000
    ) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time = get_time or time_ms
        self._storage_batch_size = storage_batch_size

    async def stream_trades(self, exchange: str, symbol: str, start: int,
                            end: int) -> AsyncIterable[Trade]:
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
                async for trade in self._stream_and_store_exchange_trades(
                    exchange, symbol, span_start, span_end
                ):
                    yield trade

    @backoff.on_exception(backoff.expo, (Exception, ), max_tries=3)
    async def _stream_and_store_exchange_trades(
        self, exchange: str, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        add_back: List[Trade] = []
        batch = []
        batch_start = start
        current = self._get_time()

        try:
            async for trade in self._stream_exchange_trades(
                exchange=exchange, symbol=symbol, start=start, end=end, current=current
            ):
                batch.append(trade)
                # We go over limit with +1 because we never take the last trade of the batch
                # because multiple trades can happen at the same time. We need our time span to be
                # correct.
                if len(batch) == self._storage_batch_size + 1:
                    del add_back[:]
                    last = batch[-1]

                    for i in range(len(batch) - 1, -1, -1):
                        if batch[i].time != last.time:
                            break
                        add_back.append(batch[i])  # Note we are adding in reverse direction.
                        del batch[i]

                    batch_end = _get_span_end(batch)
                    await self._storage.store_time_series_and_span(
                        key=(exchange, symbol),
                        type=Trade,
                        items=batch,
                        start=batch_start,
                        end=batch_end,
                    )

                    batch_start = batch_end
                    del batch[:]
                    batch.extend(add_back)
                yield trade
        finally:
            if len(batch) > 0:
                batch_end = _get_span_end(batch)
                await self._storage.store_time_series_and_span(
                    key=(exchange, symbol),
                    type=Trade,
                    items=batch,
                    start=batch_start,
                    end=batch_end,
                )

    async def _stream_exchange_trades(
        self, exchange: str, symbol: str, start: int, end: int, current: int
    ) -> AsyncIterable[Trade]:
        exchange_instance = self._exchanges[exchange]

        async def inner(stream: Optional[AsyncIterable[Trade]]) -> AsyncIterable[Trade]:
            if start < current:  # Historical.
                async for trade in exchange_instance.stream_historical_trades(
                    symbol, start, min(end, current)
                ):
                    yield trade
            if stream:  # Future.
                async for trade in stream:
                    # TODO: Can we improve? We may potentially wait for a long time before a trade
                    # past the end time occurs.
                    if trade.time >= end:
                        break

                    yield trade

        if end > current:
            async with exchange_instance.connect_stream_trades(symbol) as stream:
                async for trade in inner(stream):
                    yield trade
        else:
            async for trade in inner(None):
                yield trade


def _get_span_end(batch: List[Trade]) -> int:
    return batch[-1].time + 1
