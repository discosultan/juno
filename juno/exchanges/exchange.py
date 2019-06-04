from __future__ import annotations

from abc import abstractmethod
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Dict, Optional

from juno import (Balance, CancelOrderResult, Candle, DepthUpdate, Fees, OrderResult, OrderType,
                  OrderUpdate, Side, TimeInForce)
from juno.filters import Filters
from juno.typing import ExcType, ExcValue, Traceback


class Exchange(AbstractAsyncContextManager):

    async def __aenter__(self) -> Exchange:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    @abstractmethod
    async def map_fees(self) -> Dict[str, Fees]:
        pass

    @abstractmethod
    async def map_filters(self) -> Dict[str, Filters]:
        pass

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_balances(self) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        yield  # type: ignore

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_candles(self, symbol: str, interval: int, start: int, end: int
                                     ) -> AsyncIterator[AsyncIterable[Candle]]:
        yield  # type: ignore

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[DepthUpdate]]:
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
            test: bool = True) -> OrderResult:
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, client_id: str) -> CancelOrderResult:
        pass
