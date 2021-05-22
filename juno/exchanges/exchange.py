from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from decimal import Decimal
from types import ModuleType
from typing import AsyncIterable, AsyncIterator, Optional, TypeVar
from uuid import uuid4

from juno import Balance, Depth, OrderResult, OrderType, OrderUpdate, Side, TimeInForce

T = TypeVar('T')


class Exchange(ABC):
    # Capabilities.
    can_stream_balances: bool = False
    can_stream_depth_snapshot: bool = False  # Streams snapshot as first depth WS message.
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

    def to_exchange(self, type_: type[T], module: ModuleType) -> T:
        return next(
            t(self)
            for n, t in _list_subclasses_from_module(type_, module)
            if n == type(self).__name__
        )

    @staticmethod
    def map_to_exchanges(
        sessions: list[Exchange], type_: type[T], module: ModuleType
    ) -> dict[str, T]:
        type_sessions = {type(s).__name__: s for s in sessions}
        return {
            n.lower(): t(type_sessions[n])
            for n, t in _list_subclasses_from_module(type_, module)
            if n in type_sessions
        }

    @staticmethod
    def map_to_exchanges_combined(
        sessions: list[Exchange], type_: type[T], module: ModuleType, exchanges: list[T]
    ) -> dict[str, T]:
        return (
            Exchange.map_to_exchanges(sessions, type_, module)
            | {type(e).__name__.lower(): e for e in exchanges}
        )


def _list_subclasses_from_module(base_type: type, module: ModuleType) -> list[tuple[str, type]]:
    return inspect.getmembers(
        module,
        lambda m: inspect.isclass(m) and m is not base_type and issubclass(m, base_type),
    )
