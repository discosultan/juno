from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, AsyncIterable, Awaitable, Callable, Dict, List, Tuple

from juno import Candle, Fees, Span, SymbolInfo
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import DAY_MS, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import generate_missing_spans, list_async, merge_adjacent_spans

_log = logging.getLogger(__name__)

FetchMap = Callable[[Exchange], Awaitable[Dict[str, Any]]]


class Informant:

    def __init__(self, services: Dict[str, Any], config: Dict[str, Any]) -> None:
        self._exchanges: Dict[str, Exchange] = {
            k: v for k, v in services.items() if isinstance(v, Exchange)}
        self._storage: SQLite = services[config['storage']]

        self._exchange_data: Dict[str, Dict[type, Dict[str, Any]]] = (
            defaultdict(lambda: defaultdict(dict)))
        self._sync_tasks: List[asyncio.Task[None]] = []
        self._initial_sync_events: List[asyncio.Event] = []

    async def __aenter__(self) -> Informant:
        self._setup_sync_task(Fees, lambda e: e.map_fees())
        self._setup_sync_task(SymbolInfo, lambda e: e.map_symbol_infos())
        await asyncio.gather(*(e.wait() for e in self._initial_sync_events))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        for task in self._sync_tasks:
            task.cancel()
        await asyncio.gather(*self._sync_tasks)

    def get_fees(self, exchange: str, symbol: str) -> Fees:
        # `__all__` is a special key which allows exchange to return same fee for any symbol.
        all_fees = self._exchange_data[exchange][Fees].get('__all__')
        if all_fees:
            return all_fees
        fees = self._exchange_data[exchange][Fees].get(symbol)
        if not fees:
            raise Exception(f'Exchange {exchange} does not support symbol {symbol}')
        return fees

    def get_symbol_info(self, exchange: str, symbol: str) -> SymbolInfo:
        symbol_info = self._exchange_data[exchange][SymbolInfo].get(symbol)
        if not symbol_info:
            raise Exception(f'Exchange {exchange} does not support symbol {symbol}')
        return symbol_info

    async def stream_candles(self, exchange: str, symbol: str, interval: int, start: int, end: int
                             ) -> AsyncIterable[Tuple[Candle, bool]]:
        """Tries to stream candles for the specified range from local storage. If candles don't
        exist, streams them from an exchange and stores to local storage."""
        storage_key = (exchange, symbol, interval)

        _log.info('checking for existing candles in local storage')
        existing_spans = await list_async(
            self._storage.stream_candle_spans(storage_key, start, end))
        merged_existing_spans = list(merge_adjacent_spans(existing_spans))
        missing_spans = list(generate_missing_spans(start, end, merged_existing_spans))

        spans = ([(a, b, True) for a, b in merged_existing_spans] +
                 [(a, b, False) for a, b in missing_spans])
        spans.sort(key=lambda s: s[0])

        for span_start, span_end, exist_locally in spans:
            if exist_locally:
                _log.info(f'local candles exist between {Span(span_start, span_end)}')
                async for candle in self._storage.stream_candles(
                        storage_key, span_start, span_end):
                    yield candle, True
            else:
                _log.info(f'missing candles between {Span(span_start, span_end)}')
                async for candle, primary in self._stream_and_store_exchange_candles(
                        exchange, symbol, interval, span_start, span_end):
                    yield candle, primary

    async def _stream_and_store_exchange_candles(self, exchange: str, symbol: str, interval: int,
                                                 start: int, end: int
                                                 ) -> AsyncIterable[Tuple[Candle, bool]]:
        BATCH_SIZE = 1000
        batch = []
        batch_start = start

        async for candle, primary in self._exchanges[exchange].stream_candles(symbol, interval,
                                                                              start, end):
            if primary:
                batch.append(candle)
                if len(batch) == BATCH_SIZE:
                    batch_end = batch[-1].time + interval
                    await self._storage.store_candles_and_span((exchange, symbol, interval), batch,
                                                               batch_start, batch_end)
                    batch_start = batch_end
                    del batch[:]
            yield candle, primary

        if len(batch) > 0:
            batch_end = min(end, floor_multiple(time_ms(), interval))
            await self._storage.store_candles_and_span((exchange, symbol, interval), batch,
                                                       batch_start, batch_end)

    def _setup_sync_task(self, type_: type, fetch: FetchMap) -> None:
        initial_sync_event = asyncio.Event()
        self._initial_sync_events.append(initial_sync_event)
        self._sync_tasks.append(
            asyncio.create_task(self._sync_all_data(type_, fetch, initial_sync_event)))

    async def _sync_all_data(self, type_: type, fetch: FetchMap, initial_sync_event: asyncio.Event
                             ) -> None:
        try:
            while True:
                await asyncio.gather(
                    *(self._sync_data(e, type_, fetch) for e in self._exchanges.keys()))
                if not initial_sync_event.is_set():
                    initial_sync_event.set()
                await asyncio.sleep(DAY_MS / 1000.0)
        except asyncio.CancelledError:
            _log.info(f'{type_.__name__.lower()} sync task cancelled')
        except Exception:
            _log.exception(f'unhandled exception in {type_.__name__.lower()} sync task')

    async def _sync_data(self, exchange: str, type_: type, fetch: FetchMap) -> None:
        now = time_ms()
        data, updated = await self._storage.get_map(exchange, type_)
        if not data or not updated or now >= updated + DAY_MS:
            data = await fetch(self._exchanges[exchange])
            await self._storage.set_map(exchange, type_, data)
        self._exchange_data[exchange][type_] = data
