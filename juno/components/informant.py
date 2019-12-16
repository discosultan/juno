from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Tuple, Type, TypeVar

import backoff

from juno import Fees, Filters, ExchangeInfo, JunoException, Tickers
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

        self._synced_data: Dict[str, Dict[Type[Any], Any]] = defaultdict(dict)

    async def __aenter__(self) -> Informant:
        exchange_info_synced_evt = asyncio.Event()
        tickers_synced_evt = asyncio.Event()

        self._exchange_info_sync_task = asyncio.create_task(
            cancelable(self._sync_for_all_exchanges(
                ExchangeInfo, exchange_info_synced_evt, lambda e: e.get_exchange_info()
            ))
        )
        # TODO: Do we want to always kick this sync off? Maybe extract to a different component.
        self._tickers_sync_task = asyncio.create_task(
            cancelable(self._sync_for_all_exchanges(
                Tickers, tickers_synced_evt, lambda e: e.list_24hr_tickers()
            ))
        )

        await asyncio.gather(
            exchange_info_synced_evt.wait(),
            tickers_synced_evt.wait(),
        )

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._exchange_info_sync_task, self._tickers_sync_task)

    def get_fees_filters(self, exchange: str, symbol: str) -> Tuple[Fees, Filters]:
        exchange_info = self._synced_data[exchange][ExchangeInfo]
        fees = exchange_info.fees.get('__all__') or exchange_info.fees[symbol]
        filters = exchange_info.filters.get('__all__') or exchange_info.filters[symbol]
        return fees, filters

    def list_symbols(self, exchange: str) -> List[str]:
        return list(self._synced_data[exchange][ExchangeInfo].filters.keys())

    def list_candle_intervals(self, exchange: str) -> List[int]:
        return self._synced_data[exchange][ExchangeInfo].candle_intervals

    def list_tickers(self, exchange: str) -> Tickers:
        return self._synced_data[exchange][Tickers]

    async def _sync_for_all_exchanges(
        self, type_: Type[Any], initial_sync_event: asyncio.Event,
        fetch: Callable[[Exchange], Awaitable[Any]]
    ) -> None:
        period = DAY_MS
        _log.info(
            f'starting periodic sync of {type_.__name__} for {", ".join(self._exchanges.keys())} '
            f'every {strfinterval(period)}'
        )
        while True:
            await asyncio.gather(
                *(self._sync_for_exchange(e, type_, fetch) for e in self._exchanges.keys())
            )
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    @backoff.on_exception(backoff.expo, JunoException, max_tries=3)
    async def _sync_for_exchange(
        self, exchange: str, type_: Type[Any], fetch: Callable[[Exchange], Awaitable[Any]]
    ) -> None:
        now = time_ms()
        data, updated = await self._storage.get(exchange, type_)
        if not data or not updated:
            _log.info(
                f'local {exchange} {type_.__name__} missing; updating by fetching from exchange'
            )
            data = await self._fetch_from_exchange(exchange, type_, fetch)
        elif now >= updated + DAY_MS:
            _log.info(
                f'local {exchange} {type_.__name__} out-of-date; updating by fetching from '
                'exchange'
            )
            data = await self._fetch_from_exchange(exchange, type_, fetch)
        else:
            _log.info(f'updating {exchange} {type_.__name__} by fetching from storage')
        self._synced_data[exchange][type_] = data

    async def _fetch_from_exchange(
        self, exchange: str, type_: Type[Any], fetch: Callable[[Exchange], Awaitable[Any]]
    ) -> Any:
        data = await fetch(self._exchanges[exchange])
        await self._storage.set(exchange, type_, data)
        return data
