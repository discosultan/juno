from __future__ import annotations

from abc import ABC
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Optional
from uuid import uuid4

from juno import (
    Balance,
    Candle,
    Depth,
    ExchangeInfo,
    OrderResult,
    OrderType,
    OrderUpdate,
    SavingsProduct,
    Side,
    Ticker,
    TimeInForce,
    Trade,
    config,
    exchanges,
)
from juno.contextlib import AsyncContextManager
from juno.inspect import get_module_type


class Exchange(AsyncContextManager, ABC):
    # Capabilities.
    can_stream_balances: bool = False
    can_stream_depth_snapshot: bool = False  # Streams snapshot as first depth WS message.
    can_stream_historical_candles: bool = False
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False
    can_list_all_tickers: bool = False  # Accepts empty symbols filter to retrieve all tickers.
    can_margin_trade: bool = False
    can_place_market_order: bool = False
    can_place_market_order_quote: bool = False  # Whether market order accepts quote param.
    # TODO: Add can_receive_market_order_result_sync

    def generate_client_id(self) -> str:
        return str(uuid4())

    def list_candle_intervals(self) -> list[int]:
        raise NotImplementedError()

    async def get_exchange_info(self) -> ExchangeInfo:
        raise NotImplementedError()

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        # Empty list to disable filter.
        raise NotImplementedError()

    # Result outer key - account
    # Result inner key - asset
    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        raise NotImplementedError()

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        raise NotImplementedError()
        yield  # type: ignore

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        raise NotImplementedError()
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
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
        raise NotImplementedError()

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        raise NotImplementedError()

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        raise NotImplementedError()
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        raise NotImplementedError()
        yield  # type: ignore

    async def transfer(
        self, asset: str, size: Decimal, from_account: str, to_account: str
    ) -> None:
        raise NotImplementedError()

    async def borrow(self, asset: str, size: Decimal, account: str) -> None:
        raise NotImplementedError()

    async def repay(self, asset: str, size: Decimal, account: str) -> None:
        raise NotImplementedError()

    async def get_max_borrowable(self, asset: str, account: str) -> Decimal:
        raise NotImplementedError()

    async def get_deposit_address(self, asset: str) -> str:
        raise NotImplementedError()

    async def withdraw(self, asset: str, address: str, amount: Decimal) -> None:
        raise NotImplementedError()

    # Savings.

    async def map_savings_products(self) -> dict[str, SavingsProduct]:
        raise NotImplementedError()

    async def purchase_savings_product(self, product_id: str, size: Decimal) -> None:
        raise NotImplementedError()

    async def redeem_savings_product(self, product_id: str, size: Decimal) -> None:
        raise NotImplementedError()

    @staticmethod
    def from_env(exchange: str) -> Exchange:
        return config.init_instance(get_module_type(exchanges, exchange), config.from_env())
