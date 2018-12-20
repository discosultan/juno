import asyncio
from collections import defaultdict
import logging

from juno import Span, SymbolInfo
from juno.math import floor_multiple
from juno.time import DAY_MS, time_ms
from juno.utils import generate_missing_spans, list_async, merge_adjacent_spans


_log = logging.getLogger(__package__)


class Informant:

    def __init__(self, services, config):
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        self._storage = services[config['storage']]
        self._exchange_symbols = defaultdict(dict)

    async def __aenter__(self):
        await self._sync_all_symbol_infos()
        self._sync_task = asyncio.get_running_loop().create_task(self._period_sync())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._sync_task.cancel()
        pass

    async def _period_sync(self):
        try:
            while True:
                await asyncio.sleep(DAY_MS / 1000.0)
                await self._sync_all_symbol_infos()
        except asyncio.CancelledError:
            _log.info('periodic symbol info sync task cancelled')

    async def _sync_all_symbol_infos(self):
        return await asyncio.gather(*(self._sync_symbol_infos(e) for e in self._exchanges.keys()))

    async def _sync_symbol_infos(self, exchange):
        now = time_ms()
        infos, updated = await self._storage.get(exchange, SymbolInfo)
        if not updated or now >= updated + DAY_MS:
            infos = await self._exchanges[exchange].map_symbol_infos()
            await self._storage.store(exchange, infos)
        self._exchange_symbols[exchange] = infos

    def get_symbol_info(self, exchange, symbol):
        return self._exchange_symbols[exchange][symbol]

    async def stream_candles(self, exchange, symbol, interval, start, end):
        """Tries to stream candles for the specified range from local storage. If candles don't
        exist, streams them from an exchange and stores to local storage."""
        storage_key = (exchange, symbol, interval)

        _log.info('checking for existing candles in local storage')
        existing_spans = await list_async(
            self._storage.stream_candle_spans(storage_key, start, end))
        existing_spans = list(merge_adjacent_spans(existing_spans))
        missing_spans = generate_missing_spans(start, end, existing_spans)

        spans = ([(a, b, True) for a, b in existing_spans] +
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

    async def _stream_and_store_exchange_candles(self, exchange, symbol, interval, start, end):
        BATCH_SIZE = 500
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
