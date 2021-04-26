from abc import ABC, abstractmethod
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
    Side,
    Ticker,
    TimeInForce,
    Trade,
)


class Exchange(ABC):
    # Capabilities.
    can_stream_balances: bool = False
    can_margin_trade: bool = False
    can_place_market_order: bool = False
    can_place_market_order_quote: bool = False  # Whether market order accepts quote param.

    def generate_client_id(self) -> str:
        return str(uuid4())

    # Result outer key - account
    # Result inner key - asset
    @abstractmethod
    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        pass

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        yield  # type: ignore

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        yield  # type: ignore

    @abstractmethod
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
        pass

    @abstractmethod
    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        pass

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        yield  # type: ignore

    async def transfer(
        self, asset: str, size: Decimal, from_account: str, to_account: str
    ) -> None:
        pass

    async def borrow(self, asset: str, size: Decimal, account: str) -> None:
        pass

    async def repay(self, asset: str, size: Decimal, account: str) -> None:
        pass

    async def get_max_borrowable(self, asset: str, account: str) -> Decimal:
        pass

    async def create_account(self, account: str) -> None:
        pass

    async def list_open_accounts(self) -> list[str]:
        return ['spot']
