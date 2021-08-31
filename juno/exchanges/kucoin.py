from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from types import TracebackType
from typing import AsyncIterable, AsyncIterator, Optional

from juno import (
    Balance,
    Depth,
    ExchangeInfo,
    OrderResult,
    OrderType,
    OrderUpdate,
    Side,
    TimeInForce,
)
from juno.http import ClientSession
from juno.time import DAY_MS, HOUR_MS, MIN_MS, WEEK_MS

from .exchange import Exchange

_BASE_URL = "https://api.kucoin.com"


class KuCoin(Exchange):
    """https://docs.kucoin.com"""

    def __init__(self) -> None:
        self._session = ClientSession(raise_for_status=False, name=type(self).__name__)

    async def __aenter__(self) -> KuCoin:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    def map_candle_intervals(self) -> dict[int, int]:
        return {
            MIN_MS: 0,
            3 * MIN_MS: 0,
            5 * MIN_MS: 0,
            15 * MIN_MS: 0,
            30 * MIN_MS: 0,
            HOUR_MS: 0,
            2 * HOUR_MS: 0,
            4 * HOUR_MS: 0,
            6 * HOUR_MS: 0,
            8 * HOUR_MS: 0,
            12 * HOUR_MS: 0,
            DAY_MS: 0,
            WEEK_MS: 0,  # TODO: verify
        }

    async def get_exchange_info(self) -> ExchangeInfo:
        raise NotImplementedError()

        return ExchangeInfo()

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        if account != "spot":
            raise NotImplementedError()

        raise NotImplementedError()

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        if account != "spot":
            raise NotImplementedError()

        raise NotImplementedError()
        yield  # type: ignore

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        raise NotImplementedError()

    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        raise NotImplementedError()
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        if account != "spot":
            raise NotImplementedError()

        raise NotImplementedError()
        yield  # type: ignore

    async def place_order(
        self,
        account: str,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
    ) -> OrderResult:
        if account != "spot":
            raise NotImplementedError()

        raise NotImplementedError()

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        if account != "spot":
            raise NotImplementedError()

        raise NotImplementedError()
