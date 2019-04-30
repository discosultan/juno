from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any, AsyncIterable, Dict, Tuple

from juno import Candle, Fees, Span, SymbolInfo
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import DAY_MS, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import generate_missing_spans, list_async, merge_adjacent_spans

_log = logging.getLogger(__name__)

# TODO: Get from exchange.
_FEES = {
    'binance': Fees(maker=Decimal('0.001'), taker=Decimal('0.001')),
    # TODO: Update Coinbase fees.
    'coinbase': Fees(maker=Decimal('0.000'), taker=Decimal('0.003'))
}


class Informant:

    def __init__(self, services: Dict[str, Any], config: Dict[str, Any]) -> None:
        self._exchanges: Dict[str, Exchange] = {
            k: v for k, v in services.items() if isinstance(v, Exchange)}
        self._storage: SQLite = services[config['storage']]
        self._exchange_symbols: Dict[str, Dict[str, SymbolInfo]] = defaultdict(dict)

    async def __aenter__(self) -> Informant:
        self._initial_symbol_infos_fetched = asyncio.Event()
        self._sync_task = asyncio.create_task(self._sync_all_symbol_infos())
        await self._initial_symbol_infos_fetched.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        self._sync_task.cancel()
        await self._sync_task

    def get_fees(self, exchange: str) -> Fees:
        return _FEES[exchange]

    def get_symbol_info(self, exchange: str, symbol: str) -> SymbolInfo:
        symbol_info = self._exchange_symbols[exchange].get(symbol)
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

    async def _sync_all_symbol_infos(self) -> None:
        try:
            while True:
                await asyncio.gather(*(self._sync_symbol_infos(e) for e in self._exchanges.keys()))
                if not self._initial_symbol_infos_fetched.is_set():
                    self._initial_symbol_infos_fetched.set()
                await asyncio.sleep(DAY_MS / 1000.0)
        except asyncio.CancelledError:
            _log.info('symbol info sync task cancelled')
        except Exception:
            _log.exception('unhandled exception in symbol info sync task')

    async def _sync_symbol_infos(self, exchange: str) -> None:
        now = time_ms()
        infos, updated = await self._storage.get_map(exchange, SymbolInfo)
        if not infos or not updated or now >= updated + DAY_MS:
            infos = await self._exchanges[exchange].map_symbol_infos()
            await self._storage.set_map(exchange, SymbolInfo, infos)
        self._exchange_symbols[exchange] = infos
