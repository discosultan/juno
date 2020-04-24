from __future__ import annotations

import asyncio
import fnmatch
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, Tuple, Type, TypeVar

from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt

from juno import BorrowInfo, ExchangeException, ExchangeInfo, Fees, Filters, Ticker, Timestamp
from juno.asyncio import cancel, create_task_cancel_on_exc
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import DAY_MS, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback, get_name

_log = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class _Timestamped(Generic[T]):
    time: Timestamp
    item: T


class Informant:
    def __init__(
        self,
        storage: Storage,
        exchanges: List[Exchange],
        get_time_ms: Callable[[], int] = time_ms,
        cache_time: int = DAY_MS,
    ) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time_ms = get_time_ms
        self._cache_time = cache_time

        self._synced_data: Dict[str, Dict[Type[_Timestamped[Any]], _Timestamped[Any]]] = (
            defaultdict(dict)
        )

    async def __aenter__(self) -> Informant:
        exchange_info_synced_evt = asyncio.Event()
        tickers_synced_evt = asyncio.Event()

        self._exchange_info_sync_task = create_task_cancel_on_exc(
            self._periodic_sync_for_exchanges(
                'exchange_info',
                _Timestamped[ExchangeInfo],
                exchange_info_synced_evt,
                lambda e: e.get_exchange_info(),
                list(self._exchanges.keys()),
            )
        )
        # TODO: Do we want to always kick this sync off? Maybe extract to a different component.
        # TODO: Exchanges which don't support listing all tickers, we can do `list_symbols` first
        #       and then get tickers by symbols.
        self._tickers_sync_task = create_task_cancel_on_exc(
            self._periodic_sync_for_exchanges(
                'tickers',
                _Timestamped[List[Ticker]],
                tickers_synced_evt,
                lambda e: e.list_tickers(),
                [n for n, e in self._exchanges.items() if e.can_list_all_tickers],
            )
        )

        await asyncio.gather(
            exchange_info_synced_evt.wait(),
            tickers_synced_evt.wait(),
        )
        _log.info('ready')
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._exchange_info_sync_task, self._tickers_sync_task)

    def get_fees_filters(self, exchange: str, symbol: str) -> Tuple[Fees, Filters]:
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        fees = exchange_info.fees.get('__all__') or exchange_info.fees[symbol]
        filters = exchange_info.filters.get('__all__') or exchange_info.filters[symbol]
        return fees, filters

    def get_borrow_info(self, exchange: str, asset: str) -> BorrowInfo:
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        return exchange_info.borrow_info.get('__all__') or exchange_info.borrow_info[asset]

    def get_margin_multiplier(self, exchange) -> int:
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        return exchange_info.margin_multiplier

    def list_symbols(self, exchange: str, patterns: Optional[List[str]] = None) -> List[str]:
        all_symbols = list(
            self._synced_data[exchange][_Timestamped[ExchangeInfo]].item.filters.keys()
        )

        if patterns is None:
            return all_symbols

        # Do not use a set because we want the result ordering to be deterministic!
        # Dict is ordered.
        result: Dict[str, None] = {}
        for pattern in patterns:
            found_symbols = fnmatch.filter(all_symbols, pattern)
            if len(found_symbols) == 0:
                raise ValueError(f'Exchange {exchange} does not support any symbol matching '
                                 f'{pattern}')
            result.update({s: None for s in found_symbols})

        return list(result.keys())

    def list_candle_intervals(
        self, exchange: str, patterns: Optional[List[int]] = None
    ) -> List[int]:
        all_intervals = (
            self._synced_data[exchange][_Timestamped[ExchangeInfo]].item.candle_intervals
        )

        if patterns is None:
            return all_intervals

        result: Dict[int, None] = {}
        for pattern in patterns:
            if pattern in all_intervals:
                result[pattern] = None
            else:
                raise ValueError(f'Exchange {exchange} does not support candle interval {pattern}')

        return list(result.keys())

    def list_tickers(self, exchange: str) -> List[Ticker]:
        return self._synced_data[exchange][_Timestamped[List[Ticker]]].item

    def list_exchanges(self) -> List[str]:
        return list(self._exchanges.keys())

    def list_exchanges_supporting_symbol(self, symbol: str) -> List[str]:
        return [e for e in self._exchanges.keys() if symbol in self.list_symbols(e)]

    async def _periodic_sync_for_exchanges(
        self, key: str, type_: Type[_Timestamped[T]], initial_sync_event: asyncio.Event,
        fetch: Callable[[Exchange], Awaitable[T]], exchanges: List[str]
    ) -> None:
        period = self._cache_time
        _log.info(
            f'starting periodic sync of {key} for {", ".join(exchanges)} every '
            f'{strfinterval(period)}'
        )
        while True:
            await asyncio.gather(
                *(self._sync_for_exchange(e, key, type_, fetch) for e in exchanges)
            )
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING)
    )
    async def _sync_for_exchange(
        self, exchange: str, key: str, type_: Type[_Timestamped[T]],
        fetch: Callable[[Exchange], Awaitable[T]]
    ) -> None:
        now = self._get_time_ms()
        item = await self._storage.get(
            shard=exchange,
            key=key,
            type_=type_
        )
        if not item:
            _log.info(
                f'local {exchange} {get_name(type_)} missing; updating by fetching from exchange'
            )
            item = await self._fetch_from_exchange_and_cache(exchange, key, fetch, now)
        elif now >= item.time + self._cache_time:
            _log.info(
                f'local {exchange} {get_name(type_)} out-of-date; updating by fetching from '
                'exchange'
            )
            item = await self._fetch_from_exchange_and_cache(exchange, key, fetch, now)
        else:
            _log.info(f'updating {exchange} {get_name(type_)} by fetching from storage')
        self._synced_data[exchange][type_] = item

    async def _fetch_from_exchange_and_cache(
        self, exchange: str, key: str, fetch: Callable[[Exchange], Awaitable[T]], time: int
    ) -> _Timestamped[T]:
        item = _Timestamped(
            time=time,
            item=(await fetch(self._exchanges[exchange])),
        )
        await self._storage.set(
            shard=exchange,
            key=key,
            item=item,
        )
        return item
