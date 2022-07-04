from __future__ import annotations

import asyncio
import fnmatch
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

from tenacity import before_sleep_log, retry, retry_if_exception_type

from juno import (
    AssetInfo,
    BorrowInfo,
    ExchangeException,
    ExchangeInfo,
    Fees,
    Filters,
    Ticker,
    Timestamp,
)
from juno.asyncio import cancel, create_task_sigint_on_exception
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.tenacity import stop_after_attempt_with_reset, wait_none_then_exponential
from juno.time import HOUR_MS, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback, get_name

_log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class _Timestamped(Generic[T]):
    time: Timestamp
    item: T


class Informant:
    def __init__(
        self,
        storage: Storage,
        exchanges: list[Exchange],
        get_time_ms: Callable[[], int] = time_ms,
        cache_time: int = 6 * HOUR_MS,
    ) -> None:
        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time_ms = get_time_ms
        self._cache_time = cache_time

        self._synced_data: dict[
            str, dict[type[_Timestamped[Any]], _Timestamped[Any]]
        ] = defaultdict(dict)

    async def __aenter__(self) -> Informant:
        exchange_info_synced_evt = asyncio.Event()
        tickers_synced_evt = asyncio.Event()

        self._exchange_info_sync_task = create_task_sigint_on_exception(
            self._periodic_sync_for_exchanges(
                "exchange_info",
                _Timestamped[ExchangeInfo],
                exchange_info_synced_evt,
                lambda e: e.get_exchange_info(),
                list(self._exchanges.keys()),
            )
        )
        # TODO: Do we want to always kick this sync off? Maybe extract to a different component.
        # TODO: Exchanges which don't support listing all tickers, we can do `list_symbols` first
        #       and then get tickers by symbols.
        self._tickers_sync_task = create_task_sigint_on_exception(
            self._periodic_sync_for_exchanges(
                "tickers",
                _Timestamped[dict[str, Ticker]],
                tickers_synced_evt,
                lambda e: e.map_tickers(),
                [n for n, e in self._exchanges.items() if e.can_list_all_tickers],
            )
        )

        await asyncio.gather(
            exchange_info_synced_evt.wait(),
            tickers_synced_evt.wait(),
        )
        _log.info("ready")
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._exchange_info_sync_task, self._tickers_sync_task)

    def get_asset_info(self, exchange: str, asset: str) -> AssetInfo:
        exchange_info: ExchangeInfo = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        return _get_or_default(exchange_info.assets, asset)

    def get_fees_filters(self, exchange: str, symbol: str) -> tuple[Fees, Filters]:
        exchange_info: ExchangeInfo = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        fees = _get_or_default(exchange_info.fees, symbol)
        filters = _get_or_default(exchange_info.filters, symbol)
        return fees, filters

    def get_borrow_info(self, exchange: str, asset: str, account: str) -> BorrowInfo:
        assert account != "spot"
        exchange_info: ExchangeInfo = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        borrow_info = _get_or_default(exchange_info.borrow_info, account)
        return _get_or_default(borrow_info, asset)

    def list_symbols(
        self,
        exchange: str,
        patterns: Optional[list[str]] = None,
        spot: Optional[bool] = None,
        cross_margin: Optional[bool] = None,
        isolated_margin: Optional[bool] = None,
    ) -> list[str]:
        exchange_info: ExchangeInfo = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        all_symbols = exchange_info.filters.keys()

        result = (s for s in all_symbols)

        if patterns is not None:
            matching_symbols = {s for p in patterns for s in fnmatch.filter(all_symbols, p)}
            result = (s for s in result if s in matching_symbols)
        if spot is not None:
            result = (s for s in result if exchange_info.filters[s].spot == spot)
        if cross_margin is not None:
            result = (s for s in result if exchange_info.filters[s].cross_margin == cross_margin)
        if isolated_margin is not None:
            result = (
                s for s in result if exchange_info.filters[s].isolated_margin == isolated_margin
            )

        return list(result)

    # TODO: bound to be out-of-date with the current syncing approach
    def map_tickers(
        self,
        exchange: str,
        symbol_patterns: Optional[list[str]] = None,
        exclude_symbol_patterns: Optional[list[str]] = None,
        spot: Optional[bool] = None,
        cross_margin: Optional[bool] = None,
        isolated_margin: Optional[bool] = None,
    ) -> dict[str, Ticker]:
        exchange_info: ExchangeInfo = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        all_tickers: dict[str, Ticker] = self._synced_data[exchange][
            _Timestamped[dict[str, Ticker]]
        ].item

        result = ((s, t) for s, t in all_tickers.items())

        if symbol_patterns is not None:
            result = (
                (s, t) for s, t in result if any(fnmatch.fnmatch(s, p) for p in symbol_patterns)
            )
        if exclude_symbol_patterns:
            result = (
                (s, t)
                for s, t in result
                if not any(fnmatch.fnmatch(s, p) for p in exclude_symbol_patterns)
            )
        if spot is not None:
            result = ((s, t) for s, t in result if exchange_info.filters[s].spot == spot)
        if cross_margin is not None:
            result = (
                (s, t) for s, t in result if exchange_info.filters[s].cross_margin == cross_margin
            )
        if isolated_margin is not None:
            result = (
                (s, t)
                for s, t in result
                if exchange_info.filters[s].isolated_margin == isolated_margin
            )

        # Sorted by quote volume desc. Watch out when queried with different quote assets.
        return dict(sorted(result, key=lambda st: st[1].quote_volume, reverse=True))

    def list_exchanges(self, symbol: Optional[str] = None) -> list[str]:
        result = (e for e in self._exchanges.keys())

        if symbol is not None:
            result = (e for e in result if symbol in self.list_symbols(e))

        return list(result)

    async def _periodic_sync_for_exchanges(
        self,
        key: str,
        type_: type[_Timestamped[T]],
        initial_sync_event: asyncio.Event,
        fetch: Callable[[Exchange], Awaitable[T]],
        exchanges: list[str],
    ) -> None:
        period = self._cache_time
        _log.info(
            f'starting periodic sync of {key} for {", ".join(exchanges)} every '
            f"{strfinterval(period)}"
        )
        while True:
            await asyncio.gather(
                *(self._sync_for_exchange(e, key, type_, fetch) for e in exchanges)
            )
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    @retry(
        stop=stop_after_attempt_with_reset(8, 300),
        wait=wait_none_then_exponential(),
        retry=retry_if_exception_type(ExchangeException),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def _sync_for_exchange(
        self,
        exchange: str,
        key: str,
        type_: type[_Timestamped[T]],
        fetch: Callable[[Exchange], Awaitable[T]],
    ) -> None:
        now = self._get_time_ms()
        item = await self._storage.get(shard=exchange, key=key, type_=type_)
        if not item:
            _log.info(
                f"local {exchange} {get_name(type_)} missing; updating by fetching from exchange"
            )
            item = await self._fetch_from_exchange_and_cache(exchange, key, fetch, now)
        elif now >= item.time + self._cache_time:
            _log.info(
                f"local {exchange} {get_name(type_)} out-of-date; updating by fetching from "
                "exchange"
            )
            item = await self._fetch_from_exchange_and_cache(exchange, key, fetch, now)
        else:
            _log.info(f"updating {exchange} {get_name(type_)} by fetching from storage")
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


def _get_or_default(dictionary: dict[str, T], key: str) -> T:
    value = dictionary.get(key)
    if value is None:
        value = dictionary["__all__"]
    return value
