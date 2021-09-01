from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from types import TracebackType
from typing import Any, AsyncIterable, AsyncIterator, Optional

from juno import (
    AssetInfo,
    Balance,
    Depth,
    ExchangeException,
    ExchangeInfo,
    Fees,
    OrderResult,
    OrderType,
    OrderUpdate,
    Side,
    TimeInForce,
)
from juno.filters import Filters, Price, Size
from juno.http import ClientResponse, ClientSession
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
        currencies, symbols = await asyncio.gather(
            self._public_request_json("GET", "/api/v1/currencies"),
            self._public_request_json("GET", "/api/v1/symbols"),
        )

        assets = {
            # TODO: Maybe we should use "name" instead of "currency".
            _from_asset(c["currency"]): AssetInfo(
                precision=c["precision"]
            ) for c in currencies["data"]
        }
        fees = {
            # TODO: This is for LVL 0 only.
            "__all__": Fees(maker=Decimal("0.001"), taker=Decimal("0.001"))
        }
        filters = {
            _from_symbol(s["symbol"]): Filters(
                price=Price(
                    min=Decimal(s["quoteMinSize"]),
                    max=Decimal(s["quoteMaxSize"]),
                    step=Decimal(s["quoteIncrement"]),
                ),
                size=Size(
                    min=Decimal(s["baseMinSize"]),
                    max=Decimal(s["baseMaxSize"]),
                    step=Decimal(s["baseIncrement"]),
                )
            ) for s in symbols["data"]
        }

        return ExchangeInfo(
            assets=assets,
            fees=fees,
            filters=filters,
        )

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

    async def _public_request_json(self, method: str, url: str) -> Any:
        response = await self._request(method, url)
        response.raise_for_status()
        return await response.json()

    async def _private_request_json(self, method: str, url: str) -> Any:
        response = await self._request(method, url)
        response.raise_for_status()
        return await response.json()

    async def _request(
        self,
        method: str,
        url: str,
        # headers: Optional[dict[str, str]] = None,
        # **kwargs,
    ) -> ClientResponse:
        async with self._session.request(
            method=method,
            url=_BASE_URL + url,
            # headers=headers,
            # **kwargs,
        ) as response:
            if response.status >= 500:
                raise ExchangeException(await response.text())
            return response


def _from_asset(asset: str) -> str:
    return asset.lower()


def _from_symbol(symbol: str) -> str:
    return symbol.lower()


def _to_symbol(symbol: str) -> str:
    return symbol.upper()
