from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type, TypeVar, cast

import aiohttp
import backoff

from juno import Fees, Filters, Symbols
from juno.asyncio import cancel, cancelable
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import DAY_MS, strfinterval, strpinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)

T = TypeVar('T')

FetchMap = Callable[[Exchange], Awaitable[Symbols]]


class Informant:
    def __init__(self, storage: Storage, exchanges: List[Exchange]) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def __aenter__(self) -> Informant:
        self._symbols: Dict[str, Symbols] = {}
        self._initial_sync_event = asyncio.Event()
        self._sync_symbols_task = asyncio.create_task(cancelable(
            self._sync_all_symbols(_initial_sync_event)
        ))
        self._setup_sync_task(Fees, lambda e: e.map_symbols())
        await asyncio.gather(*(e.wait() for e in self._initial_sync_events))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(*self._sync_tasks)

    def get_fees_filters(self, exchange: str, symbol: str) -> Tuple[Fees, Filters]:
        symbols = self._symbols[exchange]
        fees = symbols.fees.get('__all__') or symbols.fees[symbol]
        filters = symbols.filters[symbol]
        return fees, filters

    def list_symbols(self, exchange: str) -> List[str]:
        return list(self._symbols[exchange].filters.keys())

    def list_intervals(self, exchange: str) -> List[int]:
        # TODO: Assumes Binance.
        intervals = [
            '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w',
            '1M'
        ]
        return list(map(strpinterval, intervals))

    async def _sync_all_symbols(self, initial_sync_event: asyncio.Event) -> None:
        period = DAY_MS
        _log.info(f'starting periodic sync of symbols every {strfinterval(period)}')
        while True:
            await asyncio.gather(*(self._sync_symbols(e) for e in self._exchanges.keys()))
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    @backoff.on_exception(
        backoff.expo, (aiohttp.ClientConnectionError, aiohttp.ClientResponseError), max_tries=3
    )
    async def _sync_symbols(self, exchange: str) -> None:
        now = time_ms()
        # symbols: Optional[Dict[str, Symbols]]
        symbols, updated = await self._storage.get_map(exchange, Symbols)
        if not symbols or not updated or now >= updated + DAY_MS:
            _log.info(f'updating symbols data by fetching from {exchange}')
            symbols = await self._exchanges[exchange].map_symbols()
            await self._storage.set_map(exchange, Symbols, symbols)
        else:
            _log.info(f'updating symbols data by fetching from storage')
        self.symbols[exchange] = symbols
