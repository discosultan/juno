from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from typing import AsyncIterable, Callable, Deque, Dict, List, Optional, Tuple

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import ExchangeException, Trade
from juno.asyncio import list_async
from juno.exchanges import Exchange
from juno.itertools import generate_missing_spans, merge_adjacent_spans
from juno.storages import Storage
from juno.tenacity import stop_after_attempt_with_reset
from juno.time import strfspan, time_ms
from juno.utils import key

_log = logging.getLogger(__name__)

TRADE_KEY = Trade.__name__.lower()


class Trades:
    def __init__(
        self,
        storage: Storage,
        exchanges: List[Exchange],
        get_time_ms: Callable[[], int] = time_ms,
        storage_batch_size: int = 1000
    ) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time_ms = get_time_ms
        self._storage_batch_size = storage_batch_size

        self._streaming_locks: Dict[Tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)

    async def stream_trades(
        self, exchange: str, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        key = (exchange, symbol)
        lock = self._streaming_locks[key]
        if lock.locked():
            _log.info(f'{key} trades are already being streamed; waiting for release')
        async with lock:
            async for trade in self._stream_trades(exchange, symbol, start, end):
                yield trade

    async def _stream_trades(
        self, exchange: str, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        """Tries to stream trades for the specified range from local storage. If trades don't
        exist, streams them from an exchange and stores to local storage."""
        shard = key(exchange, symbol)
        trade_msg = f'{exchange} {symbol} trades'

        _log.info(f'checking for existing {trade_msg} in local storage')
        existing_spans = await list_async(
            self._storage.stream_time_series_spans(
                shard=shard,
                key=TRADE_KEY,
                start=start,
                end=end,
            )
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
                stream = self._storage.stream_time_series(
                    shard=shard,
                    key=TRADE_KEY,
                    type_=Trade,
                    start=span_start,
                    end=span_end,
                )
            else:
                _log.info(f'missing {trade_msg} between {period_msg}')
                stream = self._stream_and_store_exchange_trades(
                    exchange, symbol, span_start, span_end
                )
            async for trade in stream:
                yield trade

    async def _stream_and_store_exchange_trades(
        self, exchange: str, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        shard = key(exchange, symbol)
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(3, 300),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.DEBUG)
        ):
            with attempt:
                batch = []
                swap_batch: List[Trade] = []
                batch_start = start
                current = self._get_time_ms()

                try:
                    async for trade in self._stream_exchange_trades(
                        exchange=exchange, symbol=symbol, start=start, end=end, current=current
                    ):
                        batch.append(trade)
                        # We go over limit with +1 because we never take the last trade of the
                        # batch because multiple trades can happen at the same time. We need our
                        # time span to be correct.
                        if len(batch) == self._storage_batch_size + 1:
                            last = batch[-1]

                            for i in range(len(batch) - 1, -1, -1):
                                if batch[i].time != last.time:
                                    break
                                # Note that we are inserting in front.
                                swap_batch.insert(0, batch[i])
                                del batch[i]

                            batch_end = batch[-1].time + 1
                            batch, swap_batch = swap_batch, batch
                            await self._storage.store_time_series_and_span(
                                shard=shard,
                                key=TRADE_KEY,
                                items=swap_batch,
                                start=batch_start,
                                end=batch_end,
                            )

                            batch_start = batch_end
                            del swap_batch[:]
                        yield trade
                except (asyncio.CancelledError, ExchangeException):
                    if len(batch) > 0:
                        batch_end = batch[-1].time + 1
                        await self._storage.store_time_series_and_span(
                            shard=shard,
                            key=TRADE_KEY,
                            items=batch,
                            start=batch_start,
                            end=batch[-1].time + 1,
                        )
                        start = batch_end
                    raise
                else:
                    current = self._get_time_ms()
                    batch_end = min(current, end)
                    await self._storage.store_time_series_and_span(
                        shard=shard,
                        key=TRADE_KEY,
                        items=batch,
                        start=batch_start,
                        end=batch_end,
                    )

    async def _stream_exchange_trades(
        self, exchange: str, symbol: str, start: int, end: int, current: int
    ) -> AsyncIterable[Trade]:
        exchange_instance = self._exchanges[exchange]

        async def inner(stream: Optional[AsyncIterable[Trade]]) -> AsyncIterable[Trade]:
            last_trade_ids: Deque[int] = deque(maxlen=20)
            if start < current:  # Historical.
                async for trade in exchange_instance.stream_historical_trades(
                    symbol, start, min(end, current)
                ):
                    if trade.id > 0:
                        last_trade_ids.append(trade.id)
                    yield trade
            if stream:  # Future.
                skipping_existing = True
                async for trade in stream:
                    # TODO: Can we improve? We may potentially wait for a long time before a trade
                    # past the end time occurs.
                    if trade.time >= end:
                        break

                    # Skip if trade was already retrieved from historical.
                    if skipping_existing and trade.id > 0 and trade.id in last_trade_ids:
                        continue
                    else:
                        skipping_existing = False

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
