from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import Generator, Literal, NamedTuple, Optional, Union

from juno.filters import Filters
from juno.math import precision_to_decimal, round_down, round_half_up, round_up
from juno.primitives import Asset, Interval, Interval_, Symbol, Timestamp, Timestamp_

Account = Union[Literal["spot", "margin", "isolated"], Symbol]


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


@dataclass(frozen=True)
class Balance:
    available: Decimal = Decimal("0.0")
    # TODO: Do we need it? Kraken doesn't provide that data, for example.
    hold: Decimal = Decimal("0.0")
    # Margin account related. Binance doesn't provide this through websocket!
    borrowed: Decimal = Decimal("0.0")
    interest: Decimal = Decimal("0.0")

    @property
    def repay(self) -> Decimal:
        return self.borrowed + self.interest

    @property
    def significant(self) -> bool:
        return self.available > 0 or self.hold > 0 or self.borrowed > 0 or self.interest > 0

    @staticmethod
    def zero() -> Balance:
        return Balance(available=Decimal("0.0"), hold=Decimal("0.0"))


@dataclass(frozen=True)
class BorrowInfo:
    interest_interval: Interval = Interval_.DAY
    interest_rate: Decimal = Decimal("0.0")
    limit: Decimal = Decimal("Infinity")

    def __post_init__(self) -> None:
        if self.interest_interval <= 0:
            raise ValueError("Interest interval cannot be zero or negative")
        if self.interest_rate < 0:
            raise ValueError("Interest rate cannot be negative")
        if self.limit < 0:
            raise ValueError("Borrow limit cannot be negative")


# We have a choice between dataclasses and namedtuples. Namedtuples are chosen as they support
# iterating over values of an instance (i.e `*mytuple`) which is convenient for decomposing
# values for SQLite insertion. Dataclasses miss that functionality but offer comparisons, etc.
# out of the box.
class Candle(NamedTuple):
    time: Timestamp = 0  # Interval start time.
    open: Decimal = Decimal("0.0")
    high: Decimal = Decimal("0.0")
    low: Decimal = Decimal("0.0")
    close: Decimal = Decimal("0.0")
    volume: Decimal = Decimal("0.0")  # Within interval.

    @property
    def mid(self) -> Decimal:
        return (self.open + self.close) / 2

    @property
    def midpoint(self) -> Decimal:
        return (self.high + self.low) / 2

    @property
    def mean_hlc(self) -> Decimal:
        return (self.high + self.low + self.close) / 3

    @property
    def average(self) -> Decimal:
        return (self.open + self.high + self.low + self.close) / 4

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(time={Timestamp_.to_datetime_utc(self.time)}, "
            f"open={self.open}, high={self.high}, low={self.low}, close={self.close}, "
            f"volume={self.volume})"
        )

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            "time": "unique",
        }

    @staticmethod
    def heikin_ashi(previous: Candle, current: Candle) -> Candle:
        """
        Calculates a Heikin-Ashi candle based on the formula found in
        https://www.investopedia.com/terms/h/heikinashi.asp.
        """
        open = previous.mid
        close = current.average
        return Candle(
            time=current.time,
            open=open,
            high=max(current.high, open, close),
            low=min(current.low, open, close),
            close=close,
            volume=current.volume,
        )
        # NB! Note that there are more ways to calculate Heikin-Ashi candles. For example,
        # https://school.stockcharts.com/doku.php?id=chart_analysis:heikin_ashi shows the following
        # method:
        #
        # return Candle(
        #     time=current.time,
        #     open=previous.mid,
        #     high=max(current.high, current.open, current.close),
        #     low=min(current.low, current.open, current.close),
        #     close=current.average,
        #     volume=current.volume,
        # )

    @staticmethod
    def gen_regular() -> Generator[Candle, Candle, None]:
        """
        A pass-through generator the yields the sent candles. Useful when selecting candle
        generator based on candle type.
        """
        while True:
            candle = yield  # type: ignore
            yield candle

    @staticmethod
    def gen_heikin_ashi(interval: int) -> Generator[Candle, Candle, None]:
        """
        A generator that yields Heikin-Ashi candles from sent regular candles.

        Based on the algorithm used in TradingView.
        """
        last: Optional[Candle] = None
        while True:
            current = yield  # type: ignore
            if last is None:
                previous = current
            elif current.time - last.time > interval:
                previous = current
            else:
                previous = last
            last = Candle.heikin_ashi(previous=previous, current=current)
            yield last


CandleType = Literal["regular", "heikin-ashi"]
CandleMeta = tuple[Symbol, Interval, CandleType]


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


@dataclass(frozen=True)
class Fees:
    maker: Decimal = Decimal("0.0")
    taker: Decimal = Decimal("0.0")

    def __post_init__(self) -> None:
        if self.maker < 0:
            raise ValueError("Maker fee cannot be negative")
        if self.taker < 0:
            raise ValueError("Taker fee cannot be negative")


@dataclass(frozen=True)
class AssetInfo:
    precision: int = 8

    @property
    def precision_decimal(self) -> Decimal:
        return precision_to_decimal(self.precision)

    def __post_init__(self) -> None:
        if self.precision < 0:
            raise ValueError("Precision cannot be negative")

    def round_half_up(self, value: Decimal) -> Decimal:
        return round_half_up(value, self.precision)

    def round_up(self, value: Decimal) -> Decimal:
        return round_up(value, self.precision)


@dataclass(frozen=True)
class Fill:
    price: Decimal
    size: Decimal
    quote: Decimal
    fee: Decimal = Decimal("0.0")
    fee_asset: str = "btc"

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("Trade price cannot be zero or negative")
        if self.size <= 0:
            raise ValueError("Trade size cannot be zero or negative")
        if self.quote <= 0:
            raise ValueError("Trade funds cannot be zero or negative")
        if self.fee < 0:
            raise ValueError("Trade fee cannot be negative")

    @staticmethod
    def with_computed_quote(
        price: Decimal,
        size: Decimal,
        fee: Decimal = Decimal("0.0"),
        fee_asset: str = "btc",
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
    def from_cumulative(
        fills: list[Fill],
        price: Decimal,
        cumulative_size: Decimal,
        cumulative_quote: Decimal,
        cumulative_fee: Decimal,
        fee_asset: Asset,
    ) -> Fill:
        return Fill(
            price=price,
            size=cumulative_size - Fill.total_size(fills),
            quote=cumulative_quote - Fill.total_quote(fills),
            fee=cumulative_fee - Fill.total_fee(fills, fee_asset),
            fee_asset=fee_asset,
        )

    @staticmethod
    def mean_price(fills: list[Fill]) -> Decimal:
        total_size = Fill.total_size(fills)
        return sum((f.price * f.size / total_size for f in fills), Decimal("0.0"))

    @staticmethod
    def cost(fills: list[Fill], quote_asset_precision: int) -> Decimal:
        result = Decimal("0.0")
        for fill in fills:
            result += round_half_up(fill.quote, quote_asset_precision)
        return result

    @staticmethod
    def cost_plus_fee(
        fills: list[Fill],
        base_asset: Asset,
        quote_asset: Asset,
        quote_asset_precision: int,
    ) -> Decimal:
        result = Decimal("0.0")
        for fill in fills:
            fill_gain = fill.quote
            if fill.fee_asset == quote_asset:
                fill_gain += fill.fee
            elif fill.fee_asset == base_asset:
                fill_gain += fill.fee * fill.price
            result += round_half_up(fill_gain, quote_asset_precision)
        return result

    @staticmethod
    def base_gain(
        fills: list[Fill],
        base_asset: Asset,
        quote_asset: Asset,
        base_asset_precision: int,
    ) -> Decimal:
        result = Decimal("0.0")
        for fill in fills:
            fill_gain = fill.size
            if fill.fee_asset == base_asset:
                fill_gain -= fill.fee
            elif fill.fee_asset == quote_asset:
                fill_gain -= fill.fee / fill.price
            result += round_half_up(fill_gain, base_asset_precision)
        return result

    @staticmethod
    def base_cost(fills: list[Fill], base_asset_precision) -> Decimal:
        result = Decimal("0.0")
        for fill in fills:
            result += round_half_up(fill.size, base_asset_precision)
        return result

    @staticmethod
    def gain(
        fills: list[Fill],
        base_asset: Asset,
        quote_asset: Asset,
        quote_asset_precision: int,
    ) -> Decimal:
        result = Decimal("0.0")
        for fill in fills:
            fill_gain = fill.quote
            if fill.fee_asset == quote_asset:
                fill_gain -= fill.fee
            elif fill.fee_asset == base_asset:
                fill_gain -= fill.fee * fill.price
            result += round_half_up(fill_gain, quote_asset_precision)
        return result

    @staticmethod
    def total_size(fills: list[Fill]) -> Decimal:
        return sum((f.size for f in fills), Decimal("0.0"))

    @staticmethod
    def total_quote(fills: list[Fill]) -> Decimal:
        return sum((f.quote for f in fills), Decimal("0.0"))

    @staticmethod
    def total_fee(fills: list[Fill], asset: Asset) -> Decimal:
        return sum((f.fee for f in fills if f.fee_asset == asset), Decimal("0.0"))

    @staticmethod
    def all_fees(fills: list[Fill]) -> dict[str, Decimal]:
        res: dict[str, Decimal] = defaultdict(lambda: Decimal("0.0"))
        for fill in fills:
            res[fill.fee_asset] += fill.fee
        return dict(res)

    @staticmethod
    def expected_quote(fills: list[Fill], precision: int) -> Decimal:
        return sum(
            (round_down(f.price * f.size, precision) for f in fills),
            Decimal("0.0"),
        )

    @staticmethod
    def expected_base_fee(fills: list[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * fee_rate, precision) for f in fills),
            Decimal("0.0"),
        )

    @staticmethod
    def expected_quote_fee(fills: list[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * f.price * fee_rate, precision) for f in fills),
            Decimal("0.0"),
        )


@dataclass(frozen=True)
class OrderResult:
    time: Timestamp
    status: OrderStatus
    fills: list[Fill] = field(default_factory=list)


class OrderStatus(IntEnum):
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELLED = 4
    REJECTED = 5


class OrderType(IntEnum):
    MARKET = 0
    LIMIT = 1
    # STOP_LOSS = 2
    # STOP_LOSS_LIMIT = 3
    # TAKE_PROFIT = 4
    # TAKE_PROFIT_LIMIT = 5
    LIMIT_MAKER = 6


@dataclass(frozen=True)
class Order:
    client_id: str
    symbol: Symbol
    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("Order price cannot be zero or negative")
        if self.size <= 0:
            raise ValueError("Order size cannot be zero or negative")


class CancelledReason(IntEnum):
    UNKNOWN = 0
    ORDER_WOULD_BE_TAKER = 1


class OrderUpdate(ModuleType):
    class New(NamedTuple):
        client_id: str

    # Depending on an exchange, it may return either Match or Cumulative updates.
    class Match(NamedTuple):
        client_id: str
        fill: Fill

    class Cumulative(NamedTuple):
        client_id: str
        price: Decimal
        cumulative_size: Decimal
        cumulative_quote: Decimal
        cumulative_fee: Decimal
        fee_asset: Asset

    class Cancelled(NamedTuple):
        time: Timestamp
        client_id: str
        reason: CancelledReason

    class Done(NamedTuple):
        time: Timestamp
        client_id: str

    Any = Union[New, Match, Cumulative, Cancelled, Done]


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
    # GTT = 3


class Trade(NamedTuple):
    id: int = 0  # Aggregate trade id.
    time: int = 0  # Can have multiple trades at same time.
    price: Decimal = Decimal("0.0")
    size: Decimal = Decimal("0.0")

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            "time": "index",
        }


@dataclass(frozen=True)
class ExchangeInfo:
    # Note that we use the "__all__" key convention and a regular dict instead of defaultdict for
    # easier (de)serialization.
    assets: dict[Asset, AssetInfo] = field(default_factory=lambda: {"__all__": AssetInfo()})
    fees: dict[Symbol, Fees] = field(default_factory=lambda: {"__all__": Fees()})
    filters: dict[Symbol, Filters] = field(default_factory=lambda: {"__all__": Filters()})
    borrow_info: dict[Account, dict[Asset, BorrowInfo]] = field(
        default_factory=lambda: {"__all__": {"__all__": BorrowInfo()}}
    )


@dataclass(frozen=True)
class SavingsProduct:
    product_id: str
    status: Literal["PREHEATING", "PURCHASING", "END"]
    asset: Asset
    can_purchase: bool
    can_redeem: bool
    purchased_amount: Decimal
    min_purchase_amount: Decimal
    limit: Decimal
    limit_per_user: Decimal

    @property
    def max_purchase_amount_for_user(self) -> Decimal:
        return min(self.limit - self.purchased_amount, self.limit_per_user)
