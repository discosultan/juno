from __future__ import annotations

import asyncio
import fnmatch
import itertools
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, Tuple, Type, TypeVar

from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt

from juno import BorrowInfo, ExchangeException, ExchangeInfo, Fees, Filters, Ticker, Timestamp
from juno.asyncio import cancel, create_task_cancel_on_exc
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import HOUR_MS, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback, get_name
from juno.utils import unpack_symbol

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
        cache_time: int = 6 * HOUR_MS,
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
                _Timestamped[Dict[str, Ticker]],
                tickers_synced_evt,
                lambda e: e.map_tickers(),
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

    def get_borrow_info(self, exchange: str, asset: str, account: str) -> BorrowInfo:
        assert account != 'spot'
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        borrow_info = (
            exchange_info.borrow_info.get('__all__') or exchange_info.borrow_info[account]
        )
        return borrow_info.get('__all__') or borrow_info[asset]

    # TODO: Do we need this? And the borrow param?
    def list_assets(
        self, exchange: str, patterns: Optional[List[str]] = None, borrow: bool = False
    ) -> List[str]:
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        all_assets = {a: None for a in itertools.chain(
            *(map(unpack_symbol, exchange_info.filters.keys()))
        )}

        result = (a for a in all_assets.keys())

        if patterns is not None:
            matching_assets = {a for p in patterns for a in fnmatch.filter(all_assets.keys(), p)}
            result = (a for a in result if a in matching_assets)
        if borrow:
            borrowable_assets = {a for bi in exchange_info.borrow_info.values() for a in bi.keys()}
            result = (a for a in result if a in borrowable_assets)

        return list(result)

    def list_symbols(
        self,
        exchange: str,
        patterns: Optional[List[str]] = None,
        spot: Optional[bool] = None,
        cross_margin: Optional[bool] = None,
        isolated_margin: Optional[bool] = None,
    ) -> List[str]:
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        all_symbols = exchange_info.filters.keys()

        result = (s for s in all_symbols)

        if patterns is not None:
            matching_symbols = {s for p in patterns for s in fnmatch.filter(all_symbols, p)}
            result = (s for s in result if s in matching_symbols)
        if spot is not None:
            result = (
                t for t in result
                if exchange_info.filters[t.symbol].spot == spot
            )
        if cross_margin is not None:
            result = (
                t for t in result
                if exchange_info.filters[t.symbol].cross_margin == cross_margin
            )
        if isolated_margin is not None:
            result = (
                t for t in result
                if exchange_info.filters[t.symbol].isolated_margin == isolated_margin
            )

        return list(result)

    def list_candle_intervals(
        self, exchange: str, patterns: Optional[List[int]] = None
    ) -> List[int]:
        all_intervals = self._exchanges[exchange].list_candle_intervals()

        result = (i for i in all_intervals)

        if patterns is not None:
            result = (i for i in result if i in patterns)

        return list(result)

    # TODO: bound to be out-of-date with the current syncing approach
    def map_tickers(
        self,
        exchange: str,
        symbol_patterns: Optional[List[str]] = None,
        exclude_symbol_patterns: Optional[List[str]] = None,
        spot: Optional[bool] = None,
        cross_margin: Optional[bool] = None,
        isolated_margin: Optional[bool] = None,
    ) -> Dict[str, Ticker]:
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        all_tickers = self._synced_data[exchange][_Timestamped[Dict[str, Ticker]]].item

        result = ((s, t) for s, t in all_tickers.items())

        if symbol_patterns is not None:
            result = (
                (s, t) for s, t in result if any(fnmatch.fnmatch(s, p) for p in symbol_patterns)
            )
        if exclude_symbol_patterns is not None:
            result = (
                (s, t) for s, t in result
                if not all(fnmatch.fnmatch(s, p) for p in exclude_symbol_patterns)
            )
        if spot is not None:
            result = (
                (s, t) for s, t in result
                if exchange_info.filters[s].spot == spot
            )
        if cross_margin is not None:
            result = (
                (s, t) for s, t in result
                if exchange_info.filters[s].cross_margin == cross_margin
            )
        if isolated_margin is not None:
            result = (
                (s, t) for s, t in result
                if exchange_info.filters[s].isolated_margin == isolated_margin
            )

        # Sorted by quote volume desc. Watch out when queried with different quote assets.
        return dict(sorted(result, key=lambda st: st[1].quote_volume, reverse=True))

    def list_exchanges(self, symbol: Optional[str] = None) -> List[str]:
        result = (e for e in self._exchanges.keys())

        if symbol is not None:
            result = (e for e in result if symbol in self.list_symbols(e))

        return list(result)

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
