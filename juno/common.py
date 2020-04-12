from __future__ import annotations

from decimal import Decimal
from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional, Tuple

from juno.aliases import Timestamp
from juno.filters import Filters
from juno.math import round_half_up
from juno.time import datetime_utcfromtimestamp_ms


class Advice(IntEnum):
    NONE = 0
    LONG = 1
    SHORT = 2
    LIQUIDATE = 3

    @staticmethod
    def combine(*advices: Advice) -> Advice:
        # TODO: Fix this shit, yo
        if len(advices) == 0 or any(a is Advice.NONE for a in advices):
            return Advice.NONE
        if len(set(advices)) == 1:
            return advices[0]
        return Advice.LIQUIDATE

        # if all(a is Advice.LONG for a in advices):
        #     return Advice.LONG
        # if all(a is Advice.SHORT for a in advices):
        #     return Advice.SHORT
        # if (
        #     all(a is not Advice.NONE for a in advices)
        #     and any(a is Advice.LIQUIDATE for a in advices)
        # ):
        #     return Advice.LIQUIDATE
        # return Advice.NONE


class Balance(NamedTuple):
    available: Decimal
    # TODO: Do we need it? Kraken doesn't provide that data, for example.
    hold: Decimal = Decimal('0.0')
    # Margin account related. Binance doesn't provide this through websocket!
    borrowed: Decimal = Decimal('0.0')
    interest: Decimal = Decimal('0.0')

    @property
    def repay(self) -> Decimal:
        return self.borrowed + self.interest


class BorrowInfo(NamedTuple):
    daily_interest_rate: Decimal = Decimal('0.0')
    limit: Decimal = Decimal('0.0')

    @property
    def hourly_interest_rate(self) -> Decimal:
        return self.daily_interest_rate / 24


class CancelOrderResult(NamedTuple):
    status: CancelOrderStatus


class CancelOrderStatus(IntEnum):
    SUCCESS = 0
    REJECTED = 1


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

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}(time={datetime_utcfromtimestamp_ms(self.time)}, '
            f'open={self.open}, high={self.high}, low={self.low}, close={self.close}, '
            f'volume={self.volume}, closed={self.closed})'
        )

    @staticmethod
    def meta() -> Dict[str, str]:
        return {
            'time': 'unique',
        }


class DepthSnapshot(NamedTuple):
    bids: List[Tuple[Decimal, Decimal]] = []
    asks: List[Tuple[Decimal, Decimal]] = []
    last_id: int = 0


class DepthUpdate(NamedTuple):
    bids: List[Tuple[Decimal, Decimal]] = []
    asks: List[Tuple[Decimal, Decimal]] = []
    first_id: int = 0
    last_id: int = 0


class Fees(NamedTuple):
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
        fee: Decimal,
        fee_asset: str,
        precision: int
    ) -> Fill:
        return Fill(
            price=price,
            size=size,
            quote=round_half_up(price * size, precision),
            fee=fee,
            fee_asset=fee_asset,
        )

    @staticmethod
    def total_size(fills: List[Fill]) -> Decimal:
        return sum((f.size for f in fills), Decimal('0.0'))

    @staticmethod
    def total_quote(fills: List[Fill]) -> Decimal:
        return sum((f.quote for f in fills), Decimal('0.0'))

    @staticmethod
    def total_fee(fills: List[Fill]) -> Decimal:
        # Note that we may easily have different fee assets per order when utility tokens such as
        # BNB are used.
        if len({f.fee_asset for f in fills}) > 1:
            raise NotImplementedError('Implement support for different fee assets')

        return sum((f.fee for f in fills), Decimal('0.0'))

    @staticmethod
    def expected_base_fee(fills: List[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * fee_rate, precision) for f in fills),
            Decimal('0.0'),
        )

    @staticmethod
    def expected_quote_fee(fills: List[Fill], fee_rate: Decimal, precision: int) -> Decimal:
        return sum(
            (round_half_up(f.size * f.price * fee_rate, precision) for f in fills),
            Decimal('0.0'),
        )


class OrderResult(NamedTuple):
    status: OrderStatus
    fills: List[Fill] = []

    @staticmethod
    def not_placed() -> OrderResult:
        return OrderResult(status=OrderStatus.NOT_PLACED, fills=[])


class OrderStatus(IntEnum):
    NOT_PLACED = 0
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4


class OrderType(IntEnum):
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
    price: Decimal  # Original.
    size: Decimal  # Original.
    filled_size: Decimal = Decimal('0.0')  # Last.
    filled_quote: Decimal = Decimal('0.0')  # Last.
    cumulative_filled_size: Decimal = Decimal('0.0')  # Cumulative.
    fee: Decimal = Decimal('0.0')  # Last.
    fee_asset: Optional[str] = None  # Last.


class Side(IntEnum):
    BUY = 0
    SELL = 1


class Ticker(NamedTuple):
    symbol: str
    volume: Decimal
    quote_volume: Decimal


class TimeInForce(IntEnum):
    # A Good-Til-Canceled order will continue to work within the system and in the marketplace
    # until it executes or is canceled.
    GTC = 0
    # Any portion of an Immediate-or-Cancel order that is not filled as soon as it becomes
    # available in the market is canceled.
    IOC = 1
    # If the entire Fill-or-Kill order does not execute as soon as it becomes available, the entire
    # order is canceled.
    FOK = 2


class Trade(NamedTuple):
    id: int = 0  # Aggregate trade id.
    time: int = 0  # Can have multiple trades at same time.
    price: Decimal = Decimal('0.0')
    size: Decimal = Decimal('0.0')

    @staticmethod
    def meta() -> Dict[str, str]:
        return {
            'time': 'index',
        }


class ExchangeInfo(NamedTuple):
    fees: Dict[str, Fees] = {'__all__': Fees()}
    filters: Dict[str, Filters] = {'__all__': Filters()}
    candle_intervals: List[int] = []
    borrow_info: Dict[str, BorrowInfo] = {'__all__': BorrowInfo()}
    margin_multiplier: int = 1


class JunoException(Exception):
    pass


class InsufficientBalance(JunoException):
    pass
