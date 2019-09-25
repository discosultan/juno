from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, TypeVar, cast

import aiohttp
import backoff

from juno import Fees, Filters
from juno.asyncio import cancel, cancelable
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import DAY_MS, strfinterval, strpinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)

T = TypeVar('T')

FetchMap = Callable[[Exchange], Awaitable[Dict[str, Any]]]


class Informant:
    def __init__(self, storage: Storage, exchanges: List[Exchange]) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

        self._exchange_data: Dict[str, Dict[Type[Any], Dict[str, Any]]] = (
            defaultdict(lambda: defaultdict(dict))
        )
        self._sync_tasks: List[asyncio.Task[None]] = []
        self._initial_sync_events: List[asyncio.Event] = []

    async def __aenter__(self) -> Informant:
        self._setup_sync_task(Fees, lambda e: e.map_fees())
        self._setup_sync_task(Filters, lambda e: e.map_filters())
        await asyncio.gather(*(e.wait() for e in self._initial_sync_events))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(*self._sync_tasks)

    def get_fees(self, exchange: str, symbol: str) -> Fees:
        return self._get_data(exchange, symbol, Fees)

    def get_filters(self, exchange: str, symbol: str) -> Filters:
        return self._get_data(exchange, symbol, Filters)

    def list_symbols(self, exchange: str) -> List[str]:
        # TODO: Assumes Filters is not using '__all__'.
        return list(self._exchange_data[exchange][Filters])

    def list_intervals(self, exchange: str) -> List[int]:
        # TODO: Assumes Binance.
        intervals = [
            '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w',
            '1M'
        ]
        return list(map(strpinterval, intervals))

    @backoff.on_exception(
        backoff.expo, (aiohttp.ClientConnectionError, aiohttp.ClientResponseError), max_tries=3
    )
    def _get_data(self, exchange: str, symbol: str, type_: Type[T]) -> T:
        # `__all__` is a special key which allows exchange to return same value for any symbol.
        data = self._exchange_data[exchange][type_].get('__all__')
        if not data:
            data = self._exchange_data[exchange][type_].get(symbol)
        if not data:
            raise Exception(f'Exchange {exchange} does not support symbol {symbol} for {type_}')
        _log.info(f'get {type_.__name__.lower()}: {data}')
        return cast(T, data)

    def _setup_sync_task(self, type_: type, fetch: FetchMap) -> None:
        initial_sync_event = asyncio.Event()
        self._initial_sync_events.append(initial_sync_event)
        self._sync_tasks.append(
            asyncio.create_task(cancelable(self._sync_all_data(type_, fetch, initial_sync_event)))
        )

    async def _sync_all_data(
        self, type_: type, fetch: FetchMap, initial_sync_event: asyncio.Event
    ) -> None:
        period = DAY_MS
        type_name = type_.__name__.lower()
        _log.info(f'starting periodic sync of {type_name} every {strfinterval(period)}')
        while True:
            await asyncio.gather(
                *(self._sync_data(e, type_, fetch) for e in self._exchanges.keys())
            )
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    async def _sync_data(self, exchange: str, type_: Type[T], fetch: FetchMap) -> None:
        now = time_ms()
        type_name = type_.__name__.lower()
        data: Optional[Dict[str, T]]
        data, updated = await self._storage.get_map(exchange, type_)
        if not data or not updated or now >= updated + DAY_MS:
            _log.info(f'fetching data for {type_name} from exchange')
            data = await fetch(self._exchanges[exchange])
            await self._storage.set_map(exchange, type_, data)
        else:
            _log.info(f'using data for {type_name} from storage')
        self._exchange_data[exchange][type_] = data
