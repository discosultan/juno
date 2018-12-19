import asyncio
from collections import defaultdict
import logging

from juno.math import floor_multiple
from juno.time import datetime_fromtimestamp_ms, time_ms
from juno.utils import generate_missing_spans, list_async, merge_adjacent_spans


_log = logging.getLogger(__package__)


class Informant:

    def __init__(self, services, config):
        self._exchanges = {s.__class__.__name__.lower(): s for s in services.values()
                           if s.__class__.__name__.lower() in config['exchanges']}
        _log.info(self._exchanges)
        self._storage = services[config['storage']]
        self._exchange_symbols = defaultdict(dict)

    async def __aenter__(self):
        s_infos = await asyncio.gather(*(e.map_symbol_infos() for e in self._exchanges.values()))
        for exchange, symbol_infos in zip(self._exchanges.keys(), s_infos):
            self._exchange_symbols[exchange] = symbol_infos
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

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
                _log.info('local candles exist between '
                          f'{map(datetime_fromtimestamp_ms, (span_start, span_end))}')
                async for candle in self._storage.stream_candles(
                        storage_key, span_start, span_end):
                    yield candle, True
            else:
                _log.info('missing candles between '
                          f'{map(datetime_fromtimestamp_ms, (span_start, span_end))}')
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
