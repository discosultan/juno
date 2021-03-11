from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import NamedTuple, Optional, Union

from juno.aliases import Timestamp
from juno.filters import Filters
from juno.math import round_down, round_half_up
from juno.time import datetime_utcfromtimestamp_ms


class Advice(IntEnum):
    NONE = 0
    LONG = 1
    SHORT = 2
    LIQUIDATE = 3

    @staticmethod
    def combine(*advices: Advice) -> Advice:
        if len(advices) == 0 or any(a is Advice.NONE for a in advices):
            return Advice.NONE
        if len(set(advices)) == 1:
            return advices[0]
        return Advice.LIQUIDATE


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


@dataclass
class BorrowInfo:
    daily_interest_rate: Decimal = Decimal('0.0')
    limit: Decimal = Decimal('0.0')

    @property
    def hourly_interest_rate(self) -> Decimal:
        return self.daily_interest_rate / 24


# We have a choice between dataclasses and namedtuples. Namedtuples are chosen as they support
# iterating over values of an instance (i.e `*mytuple`) which is convenient for decomposing
# values for SQLIte insertion. Dataclasses miss that functionality but offer comparisons, etc.
# out of the box.
class Candle(NamedTuple):
    time: Timestamp = 0  # Interval start time.
    open: Decimal = Decimal('0.0')
    high: Decimal = Decimal('0.0')
    low: Decimal = Decimal('0.0')
    close: Decimal = Decimal('0.0')
    volume: Decimal = Decimal('0.0')  # Within interval.
    closed: bool = True

    @property
    def midpoint(self) -> Decimal:
        return (self.open + self.close) / 2

    @property
    def mean_hlc(self) -> Decimal:
        return (self.high + self.low + self.close) / 3

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}(time={datetime_utcfromtimestamp_ms(self.time)}, '
            f'open={self.open}, high={self.high}, low={self.low}, close={self.close}, '
            f'volume={self.volume}, closed={self.closed})'
        )

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            'time': 'unique',
        }


class Depth(ModuleType):
    class Snapshot(NamedTuple):
        bids: list[tuple[Decimal, Decimal]] = []
        asks: list[tuple[Decimal, Decimal]] = []
        last_id: int = 0

    class Update(NamedTuple):
        bids: list[tuple[Decimal, Decimal]] = []
        asks: list[tuple[Decimal, Decimal]] = []
        first_id: int = 0
        last_id: int = 0

    Any = Union[Snapshot, Update]


@dataclass
class Fees:
    maker: Decimal = Decimal('0.0')
    taker: Decimal = Decimal('0.0')


class Fill(NamedTuple):
    price: Decimal = Decimal('0.0')
    size: Decimal = Decimal('0.0')
    quote: Decimal = Decimal('0.0')
    fee: Decimal = Decimal('0.0')
    fee_asset: str = 'btc'

    @staticmethod
    def with_computed_quote(
        price: Decimal,
        size: Decimal,
        fee: Decimal = Decimal('0.0'),
        fee_asset: str = 'btc',
        precision: Optional[int] = None,
    ) -> Fill:
        quote = price * size
        return Fill(
            price=price,
            size=size,
            quote=round_down(quote, precision) if precision is not None else quote,
            fee=fee,
            fee_asset=fee_asset,
        )

    @staticmethod
    def mean_price(fills: list[Fill]) -> Decimal:
        total_size = Fill.total_size(fills)
        return sum((f.price * f.size / total_size for f in fills), Decimal('0.0'))

    @staticmethod
    def total_size(fills: list[Fill]) -> Decimal:
        return sum((f.size for f in fills), Decimal('0.0'))

    @staticmethod
    def total_quote(fills: list[Fill]) -> Decimal:
        return sum((f.quote for f in fills), Decimal('0.0'))

    @staticmethod
    def total_fee(fills: list[Fill], asset: str) -> Decimal:
        return sum((f.fee for f in fills if f.fee_asset == asset), Decimal('0.0'))

    @staticmethod
    def all_fees(fills: list[Fill]) -> dict[str, Decimal]:
        res: dict[str, Decimal] = defaultdict(lambda: Decimal('0.0'))
        for fill in fills:
            res[fill.fee_asset] += fill.fee
        return dict(res)

    @staticmethod
    def expected_quote(fills: list[Fill], precision: int) -> Decimal:
        return sum(
            (round_down(f.price * f.size, precision) for f in fills),
            Decimal('0.0'),
        )

    @staticmethod
    def expected_base_fee(fills: list[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * fee_rate, precision) for f in fills),
            Decimal('0.0'),
        )

    @staticmethod
    def expected_quote_fee(fills: list[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * f.price * fee_rate, precision) for f in fills),
            Decimal('0.0'),
        )


class MissedCandlePolicy(IntEnum):
    IGNORE = 0
    RESTART = 1
    LAST = 2


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
    STOP_LOSS = 2
    STOP_LOSS_LIMIT = 3
    TAKE_PROFIT = 4
    TAKE_PROFIT_LIMIT = 5
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


class Side(IntEnum):
    BUY = 0
    SELL = 1


class Ticker(NamedTuple):
    volume: Decimal  # 24h.
    quote_volume: Decimal  # 24h.
    price: Decimal  # Last.


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
    GTT = 3


class Trade(NamedTuple):
    id: int = 0  # Aggregate trade id.
    time: int = 0  # Can have multiple trades at same time.
    price: Decimal = Decimal('0.0')
    size: Decimal = Decimal('0.0')

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            'time': 'index',
        }


@dataclass
class ExchangeInfo:
    # Key: asset
    assets: dict[str, AssetInfo] = field(default_factory=lambda: {'__all__': AssetInfo()})
    # Key: symbol
    fees: dict[str, Fees] = field(default_factory=lambda: {'__all__': Fees()})
    # Key: symbol
    filters: dict[str, Filters] = field(default_factory=lambda: {'__all__': Filters()})
    # Keys: account, asset
    borrow_info: dict[str, dict[str, BorrowInfo]] = field(
        default_factory=lambda: {'__all__': {'__all__': BorrowInfo()}}
    )


@dataclass
class AssetInfo:
    precision: int = 8
