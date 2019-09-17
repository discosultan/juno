from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import List, NamedTuple, Optional, Tuple

from juno.time import datetime_utcfromtimestamp_ms


class Advice(Enum):
    NONE = 0
    BUY = 1
    SELL = 2


class Balance(NamedTuple):
    available: Decimal
    hold: Decimal


class CancelOrderResult(NamedTuple):
    status: CancelOrderStatus


class CancelOrderStatus(Enum):
    SUCCESS = 0
    REJECTED = 1


# We have a choice between dataclasses and namedtuples. Namedtuples are chosen as they support
# iterating over values of an instance (i.e `*mytuple`) which is convenient for decomposing
# values for SQLIte insertion. Dataclasses miss that functionality but offer comparisons, etc.
# out of the box.
class Candle(NamedTuple):
    time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    closed: bool

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}(time={datetime_utcfromtimestamp_ms(self.time)}, '
            f'open={self.open}, high={self.high}, low={self.low}, close={self.close}, '
            f'volume={self.volume}, closed={self.closed})'
        )


class DepthUpdate(NamedTuple):
    type: DepthUpdateType
    bids: List[Tuple[Decimal, Decimal]]
    asks: List[Tuple[Decimal, Decimal]]


class DepthUpdateType(Enum):
    SNAPSHOT = 0
    UPDATE = 1


class Fees(NamedTuple):
    maker: Decimal
    taker: Decimal

    @staticmethod
    def none() -> Fees:
        return Fees(maker=Decimal(0), taker=Decimal(0))


class Fill(NamedTuple):
    price: Decimal
    size: Decimal
    fee: Decimal
    fee_asset: str


class Fills(List[Fill]):
    @property
    def total_size(self) -> Decimal:
        return sum((f.size for f in self), Decimal(0))

    @property
    def total_quote(self) -> Decimal:
        return sum((f.size * f.price for f in self), Decimal(0))

    @property
    def total_fee(self) -> Decimal:
        # Note that we may easily have different fee assets per order when utility tokens such as
        # BNB are used.
        if len(set((f.fee_asset for f in self))) > 1:
            raise NotImplementedError('implement support for different fee assets')

        return sum((f.fee for f in self), Decimal(0))


class Side(Enum):
    BUY = 0
    SELL = 1


class OrderResult(NamedTuple):
    status: OrderStatus
    fills: Fills

    @staticmethod
    def not_placed() -> OrderResult:
        return OrderResult(status=OrderStatus.NOT_PLACED, fills=Fills())


class OrderStatus(Enum):
    NOT_PLACED = 0
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4


class OrderType(Enum):
    MARKET = 0
    LIMIT = 1
    STOP_LOSS = 2
    STOP_LOSS_LIMIT = 3
    TAKE_PROFIT = 4
    TAKE_PROFIT_LIMIT = 5
    LIMIT_MAKER = 6


class OrderUpdate(NamedTuple):
    symbol: str
    status: OrderStatus
    client_id: str
    price: Decimal
    size: Decimal
    cumulative_filled_size: Decimal
    fee: Decimal
    fee_asset: Optional[str]


class TimeInForce(Enum):
    # A Good-Til-Canceled order will continue to work within the system and in the marketplace
    # until it executes or is canceled.
    GTC = 0
    # Any portion of an Immediate-or-Cancel order that is not filled as soon as it becomes
    # available in the market is canceled.
    IOC = 1
    # If the entire Fill-or-Kill order does not execute as soon as it becomes available, the entire
    # order is canceled.
    FOK = 2


class Trend(Enum):
    UNKNOWN = 0
    UP = 1
    DOWN = 2
