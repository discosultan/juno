from __future__ import annotations

from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import NamedTuple, Union

from juno.aliases import Timestamp
from juno.orderbook import Fill


class Balance(NamedTuple):
    available: Decimal = Decimal('0.0')
    # TODO: Do we need it? Kraken doesn't provide that data, for example.
    hold: Decimal = Decimal('0.0')
    # Margin account related. Binance doesn't provide this through websocket!
    borrowed: Decimal = Decimal('0.0')
    interest: Decimal = Decimal('0.0')

    @property
    def repay(self) -> Decimal:
        return self.borrowed + self.interest

    @property
    def significant(self) -> bool:
        return (
            self.available > 0
            or self.hold > 0
            or self.borrowed > 0
            or self.interest > 0
        )


class OrderResult(NamedTuple):
    time: Timestamp
    status: OrderStatus
    fills: list[Fill] = []


class OrderStatus(IntEnum):
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELLED = 4


class OrderType(IntEnum):
    MARKET = 0
    LIMIT = 1
    # STOP_LOSS = 2
    # STOP_LOSS_LIMIT = 3
    # TAKE_PROFIT = 4
    # TAKE_PROFIT_LIMIT = 5
    LIMIT_MAKER = 6


class Order(NamedTuple):
    client_id: str
    symbol: str
    price: Decimal
    size: Decimal


class OrderUpdate(ModuleType):
    class New(NamedTuple):
        client_id: str

    class Match(NamedTuple):
        client_id: str
        fill: Fill

    class Cancelled(NamedTuple):
        time: Timestamp
        client_id: str

    class Done(NamedTuple):
        time: Timestamp
        client_id: str

    Any = Union[New, Match, Cancelled, Done]


class TimeInForce(IntEnum):
    # A Good-Til-Cancelled order will continue to work within the system and in the marketplace
    # until it executes or is cancelled.
    GTC = 0
    # Any portion of an Immediate-or-Cancel order that is not filled as soon as it becomes
    # available in the market is cancelled.
    IOC = 1
    # If the entire Fill-or-Kill order does not execute as soon as it becomes available, the entire
    # order is cancelled.
    FOK = 2
    # A Good-Til-Time orders remain open on the book until cancelled or the allotted time is
    # depleted on the matching engine.
    # GTT = 3