from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Tuple, TypeVar

import backoff

from juno import Fees, Filters, SymbolsInfo
from juno.asyncio import cancel, cancelable
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import DAY_MS, strfinterval, strpinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)

T = TypeVar('T')

FetchMap = Callable[[Exchange], Awaitable[SymbolsInfo]]


class Informant:
    def __init__(self, storage: Storage, exchanges: List[Exchange]) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def __aenter__(self) -> Informant:
        self._symbols_infos: Dict[str, SymbolsInfo] = {}
        self._initial_sync_event = asyncio.Event()
        self._sync_task = asyncio.create_task(cancelable(
            self._sync_all_symbols(self._initial_sync_event)
        ))
        await self._initial_sync_event.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_task)

    def get_fees_filters(self, exchange: str, symbol: str) -> Tuple[Fees, Filters]:
        symbol_info = self._symbols_infos[exchange]
        fees = symbol_info.fees.get('__all__') or symbol_info.fees[symbol]
        filters = symbol_info.filters.get('__all__') or symbol_info.filters[symbol]
        return fees, filters

    def list_symbols(self, exchange: str) -> List[str]:
        return list(self._symbols_infos[exchange].filters.keys())

    def list_intervals(self, exchange: str) -> List[int]:
        # TODO: Assumes Binance.
        intervals = [
            '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w',
            '1M'
        ]
        return list(map(strpinterval, intervals))

    async def _sync_all_symbols(self, initial_sync_event: asyncio.Event) -> None:
        period = DAY_MS
        _log.info(f'starting periodic sync of symbol info for {", ".join(self._exchanges.keys())} '
                  f'every {strfinterval(period)}')
        while True:
            await asyncio.gather(*(self._sync_symbols(e) for e in self._exchanges.keys()))
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    @backoff.on_exception(backoff.expo, (Exception,), max_tries=3)
    async def _sync_symbols(self, exchange: str) -> None:
        now = time_ms()
        symbols_info, updated = await self._storage.get(exchange, SymbolsInfo)
        if not symbols_info or not updated or now >= updated + DAY_MS:
            _log.info(f'updating symbol info by fetching from {exchange}')
            symbols_info = await self._exchanges[exchange].get_symbols_info()
            await self._storage.set(exchange, SymbolsInfo, symbols_info)
        else:
            _log.info(f'updating symbol info by fetching from storage')
        self._symbols_infos[exchange] = symbols_info
