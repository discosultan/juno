from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Tuple, TypeVar

import backoff

from juno import Fees, Filters, ExchangeInfo
from juno.asyncio import cancel, cancelable
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import DAY_MS, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)

T = TypeVar('T')

FetchMap = Callable[[Exchange], Awaitable[ExchangeInfo]]


class Informant:
    def __init__(self, storage: Storage, exchanges: List[Exchange]) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def __aenter__(self) -> Informant:
        self._exchange_infos: Dict[str, ExchangeInfo] = {}
        self._initial_sync_event = asyncio.Event()
        self._sync_task = asyncio.create_task(
            cancelable(self._sync_all_symbols(self._initial_sync_event))
        )
        await self._initial_sync_event.wait()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._sync_task)

    def get_fees_filters(self, exchange: str, symbol: str) -> Tuple[Fees, Filters]:
        exchange_info = self._exchange_infos[exchange]
        fees = exchange_info.fees.get('__all__') or exchange_info.fees[symbol]
        filters = exchange_info.filters.get('__all__') or exchange_info.filters[symbol]
        return fees, filters

    def list_symbols(self, exchange: str) -> List[str]:
        return list(self._exchange_infos[exchange].filters.keys())

    def list_candle_intervals(self, exchange: str) -> List[int]:
        return self._exchange_infos[exchange].candle_intervals

    async def _sync_all_symbols(self, initial_sync_event: asyncio.Event) -> None:
        period = DAY_MS
        _log.info(
            f'starting periodic sync of symbol info for {", ".join(self._exchanges.keys())} '
            f'every {strfinterval(period)}'
        )
        while True:
            await asyncio.gather(*(self._sync_exchange_infos(e) for e in self._exchanges.keys()))
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def _sync_exchange_infos(self, exchange: str) -> None:
        now = time_ms()
        exchange_info, updated = await self._storage.get(exchange, ExchangeInfo)
        if not exchange_info or not updated:
            _log.info(f'local {exchange} symbols info missing; updating by fetching from exchange')
            exchange_info = await self._fetch_exchange_info(exchange)
        elif now >= updated + DAY_MS:
            _log.info(
                f'local {exchange} symbols info out-of-date; updating by fetching from '
                'exchange'
            )
            exchange_info = await self._fetch_exchange_info(exchange)
        else:
            _log.info(f'updating {exchange} symbols info by fetching from storage')
        self._exchange_infos[exchange] = exchange_info

    async def _fetch_exchange_info(self, exchange: str) -> ExchangeInfo:
        exchange_info = await self._exchanges[exchange].get_exchange_info()
        await self._storage.set(exchange, ExchangeInfo, exchange_info)
        return exchange_info
