from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Dict, List, Optional

from juno import (
    AccountType, Balance, Candle, Depth, ExchangeInfo, IsolatedMarginBalance, OrderResult,
    OrderType, OrderUpdate, Side, Ticker, TimeInForce, Trade
)


class Exchange(ABC):
    # Capabilities.
    can_stream_balances: bool = False
    can_stream_depth_snapshot: bool = False  # Streams snapshot as first depth WS message.
    can_stream_historical_candles: bool = False
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False
    can_list_all_tickers: bool = False  # Accepts empty symbols filter to retrieve all tickers.
    can_margin_trade: bool = False
    can_place_order_market_quote: bool = False  # Whether market order accepts quote param.

    @abstractmethod
    async def get_exchange_info(self) -> ExchangeInfo:
        pass

    async def list_tickers(self, symbols: List[str] = []) -> List[Ticker]:
        # Empty list to disable filter.
        pass

    @abstractmethod
    async def map_balances(self, margin: bool = False) -> Dict[str, Balance]:
        pass

    async def map_isolated_margin_balances(self) -> Dict[str, IsolatedMarginBalance]:
        pass

    @asynccontextmanager
    async def connect_stream_balances(
        self, margin: bool = False
    ) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        yield  # type: ignore

    @abstractmethod
    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        yield  # type: ignore

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        raise NotImplementedError()

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        yield  # type: ignore

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_orders(
        self, symbol: str, account: AccountType = AccountType.SPOT
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        yield  # type: ignore

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
        account: AccountType = AccountType.SPOT,
        test: bool = True,
    ) -> OrderResult:
        pass

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        client_id: str,
        account: AccountType = AccountType.SPOT,
    ) -> None:
        pass

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        yield  # type: ignore

    async def transfer(self, asset: str, size: Decimal, margin: bool) -> None:
        pass

    async def transfer_isolated(
        self, asset: str, symbol: str, from_margin: bool, to_margin: bool, size: Decimal
    ) -> None:
        pass

    async def borrow(
        self, asset: str, size: Decimal, isolated: bool = False,
        isolated_symbol: Optional[str] = None
    ) -> None:
        pass

    async def repay(
        self, asset: str, size: Decimal, isolated: bool = False,
        isolated_symbol: Optional[str] = None
    ) -> None:
        pass

    async def get_max_borrowable(
        self, asset: str, isolated_symbol: Optional[str] = None
    ) -> Decimal:
        pass
