from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Optional
from uuid import uuid4

from juno import (
    Account,
    Asset,
    Balance,
    Candle,
    ClientId,
    Depth,
    ExchangeInfo,
    Interval,
    OrderResult,
    OrderType,
    OrderUpdate,
    SavingsProduct,
    Side,
    Symbol,
    Ticker,
    TimeInForce,
    Timestamp,
    Trade,
    config,
    exchanges,
)
from juno.contextlib import AsyncContextManager
from juno.inspect import get_module_type


class Exchange(AsyncContextManager, ABC):
    # Capabilities.

    can_stream_balances: bool = False
    # Streams snapshot as first depth WS message.
    can_stream_depth_snapshot: bool = False
    can_stream_historical_candles: bool = False
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False
    # Accepts empty symbols filter to retrieve all tickers.
    can_list_all_tickers: bool = False
    can_margin_trade: bool = False
    can_place_market_order: bool = False
    # Whether market order accepts quote param.
    can_place_market_order_quote: bool = False
    # If order can be edited directly or has to be cancelled and recreated.
    can_edit_order: bool = False
    can_edit_order_atomic: bool = False
    # TODO: Add can_receive_market_order_result_sync

    def generate_client_id(self) -> int | str:
        return str(uuid4())

    def list_candle_intervals(self) -> list[int]:
        raise NotImplementedError()

    @abstractmethod
    async def get_exchange_info(self) -> ExchangeInfo:
        raise NotImplementedError()

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        # Empty list to disable filter.
        raise NotImplementedError()

    # Result outer key - account
    # Result inner key - asset
    async def map_balances(self, account: Account) -> dict[str, dict[str, Balance]]:
        raise NotImplementedError()

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: Account
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        raise NotImplementedError()
        yield  # type: ignore

    async def stream_historical_candles(
        self, symbol: Symbol, interval: Interval, start: Timestamp, end: Timestamp
    ) -> AsyncIterable[Candle]:
        raise NotImplementedError()
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: Symbol, interval: Interval
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        raise NotImplementedError()
        yield  # type: ignore

    async def get_depth(self, symbol: Symbol) -> Depth.Snapshot:
        raise NotImplementedError()

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: Symbol
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        raise NotImplementedError()
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: Account, symbol: Symbol
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        raise NotImplementedError()
        yield  # type: ignore

    async def place_order(
        self,
        account: Account,
        symbol: Symbol,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[ClientId] = None,
    ) -> OrderResult:
        raise NotImplementedError()

    async def edit_order(
        self,
        existing_id: ClientId,
        account: Account,
        symbol: Symbol,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[ClientId] = None,
    ) -> OrderResult:
        raise NotImplementedError()

    async def cancel_order(
        self,
        account: Account,
        symbol: Symbol,
        client_id: ClientId,
    ) -> None:
        raise NotImplementedError()

    async def stream_historical_trades(
        self, symbol: Symbol, start: Timestamp, end: Timestamp
    ) -> AsyncIterable[Trade]:
        raise NotImplementedError()
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: Symbol) -> AsyncIterator[AsyncIterable[Trade]]:
        raise NotImplementedError()
        yield  # type: ignore

    async def transfer(
        self, asset: Asset, size: Decimal, from_account: Account, to_account: Account
    ) -> None:
        raise NotImplementedError()

    async def borrow(self, asset: Asset, size: Decimal, account: Account) -> None:
        raise NotImplementedError()

    async def repay(self, asset: Asset, size: Decimal, account: Account) -> None:
        raise NotImplementedError()

    async def get_max_borrowable(self, asset: Asset, account: Account) -> Decimal:
        raise NotImplementedError()

    async def get_deposit_address(self, asset: Asset) -> str:
        raise NotImplementedError()

    async def withdraw(self, asset: Asset, address: str, amount: Decimal) -> None:
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
