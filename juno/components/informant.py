from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type, TypeVar

from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt

from juno import ExchangeInfo, Fees, Filters, JunoException, Ticker
from juno.asyncio import cancel, cancelable
from juno.exchanges import Exchange
from juno.storages import Storage
from juno.time import DAY_MS, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback, get_name
from juno.utils import unpack_symbol

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
            cancelable(self._periodic_sync_for_exchanges(
                ExchangeInfo,
                exchange_info_synced_evt,
                lambda e: e.get_exchange_info(),
                list(self._exchanges.keys())
            ))
        )
        # TODO: Do we want to always kick this sync off? Maybe extract to a different component.
        # TODO: Exchanges which don't support listing all tickers, we can do `list_symbols` first
        #       and then get tickers by symbols.
        self._tickers_sync_task = asyncio.create_task(
            cancelable(self._periodic_sync_for_exchanges(
                List[Ticker],
                tickers_synced_evt,
                lambda e: e.list_tickers(),
                [n for n, e in self._exchanges.items() if e.can_list_all_tickers]
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

    def list_symbols(self, exchange: str, patterns: Optional[List[str]] = None) -> List[str]:
        all_symbols = list(self._synced_data[exchange][ExchangeInfo].filters.keys())

        if patterns is None:
            return all_symbols

        # Do not use a set because we want the result ordering to be deterministic!
        # Dict is ordered.
        result: Dict[str, None] = {}
        for pattern in patterns:
            added = 0
            base_pattern, quote_pattern = unpack_symbol(pattern)
            for symbol in all_symbols:
                base_asset, quote_asset = unpack_symbol(symbol)
                match = True
                if base_pattern != '*' and base_pattern != base_asset:
                    match = False
                if quote_pattern != '*' and quote_pattern != quote_asset:
                    match = False
                if match:
                    result[symbol] = None
                    added += 1
            if added == 0:
                raise ValueError(f'Exchange {exchange} does not support any symbol matching '
                                 f'{pattern}')

        return list(result.keys())

    def list_candle_intervals(
        self, exchange: str, patterns: Optional[List[int]] = None
    ) -> List[int]:
        all_intervals = self._synced_data[exchange][ExchangeInfo].candle_intervals

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
        return self._synced_data[exchange][List[Ticker]]

    def list_exchanges(self) -> List[str]:
        return list(self._exchanges.keys())

    def list_exchanges_supporting_symbol(self, symbol: str) -> List[str]:
        return [e for e in self._exchanges.keys() if symbol in self.list_symbols(e)]

    async def _periodic_sync_for_exchanges(
        self, type_: Type[Any], initial_sync_event: asyncio.Event,
        fetch: Callable[[Exchange], Awaitable[Any]], exchanges: List[str]
    ) -> None:
        period = DAY_MS
        _log.info(
            f'starting periodic sync of {get_name(type_)} for {", ".join(exchanges)} every '
            f'{strfinterval(period)}'
        )
        while True:
            await asyncio.gather(
                *(self._sync_for_exchange(e, type_, fetch) for e in exchanges)
            )
            if not initial_sync_event.is_set():
                initial_sync_event.set()
            await asyncio.sleep(period / 1000.0)

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(JunoException),
        before_sleep=before_sleep_log(_log, logging.DEBUG)
    )
    async def _sync_for_exchange(
        self, exchange: str, type_: Type[Any], fetch: Callable[[Exchange], Awaitable[Any]]
    ) -> None:
        now = time_ms()
        data, updated = await self._storage.get(exchange, type_)
        if not data or not updated:
            _log.info(
                f'local {exchange} {get_name(type_)} missing; updating by fetching from exchange'
            )
            data = await self._fetch_from_exchange(exchange, type_, fetch)
        elif now >= updated + DAY_MS:
            _log.info(
                f'local {exchange} {get_name(type_)} out-of-date; updating by fetching from '
                'exchange'
            )
            data = await self._fetch_from_exchange(exchange, type_, fetch)
        else:
            _log.info(f'updating {exchange} {get_name(type_)} by fetching from storage')
        self._synced_data[exchange][type_] = data

    async def _fetch_from_exchange(
        self, exchange: str, type_: Type[Any], fetch: Callable[[Exchange], Awaitable[Any]]
    ) -> Any:
        data = await fetch(self._exchanges[exchange])
        await self._storage.set(exchange, type_, data)
        return data
