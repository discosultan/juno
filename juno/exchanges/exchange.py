from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Dict, Optional, Union

from juno import (
    Balance, CancelOrderResult, Candle, DepthSnapshot, DepthUpdate, OrderResult, OrderType,
    OrderUpdate, Side, SymbolsInfo, TimeInForce
)


class Exchange(ABC):
    def __init__(self, depth_ws_snapshot: bool = False) -> None:
        self.depth_ws_snapshot = depth_ws_snapshot

    @abstractmethod
    async def get_symbols_info(self) -> SymbolsInfo:
        pass

    # @abstractmethod
    # async def get_balances(self) -> Dict[str, Balance]:
    #     pass

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_balances(self) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        yield  # type: ignore

    @abstractmethod
    async def stream_historical_candles(self, symbol: str, interval: int, start: int,
                                        end: int) -> AsyncIterable[Candle]:
        yield  # type: ignore

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_future_candles(self, symbol: str,
                                            interval: int) -> AsyncIterator[AsyncIterable[Candle]]:
        yield  # type: ignore

    async def get_depth(self, symbol: str) -> DepthSnapshot:
        raise NotImplementedError()

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Union[DepthSnapshot, DepthUpdate]]]:
        yield  # type: ignore

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_orders(self) -> AsyncIterator[AsyncIterable[OrderUpdate]]:
        yield  # type: ignore

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Decimal,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
        test: bool = True
    ) -> OrderResult:
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, client_id: str) -> CancelOrderResult:
        pass
