from __future__ import annotations

from collections import namedtuple
from decimal import Decimal
from enum import Enum
from typing import List, NamedTuple

from juno.time import datetime_utcfromtimestamp_ms

AccountInfo = namedtuple('AccountInfo', ['time', 'base_balance', 'quote_balance', 'fees'])
# BidAsk = namedtuple('BidAsk', ['price', 'size'])
# Depth = namedtuple('Depth', ['bids', 'asks'])
Trade = namedtuple('Trade', ['price', 'size', 'commission', 'commission_asset', 'is_buyer'])


class Balance(NamedTuple):
    available: Decimal
    hold: Decimal


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

    def __repr__(self) -> str:
        return (f'{type(self).__name__}(time={datetime_utcfromtimestamp_ms(self.time)}, '
                f'open={self.open}, high={self.high}, low={self.low}, close={self.close})')


class Fees(NamedTuple):
    maker: Decimal
    taker: Decimal

    @staticmethod
    def zero() -> Fees:
        return Fees(maker=Decimal(0), taker=Decimal(0))


class Span(NamedTuple):
    start: int
    end: int

    def __repr__(self) -> str:
        return (f'{type(self).__name__}(start={datetime_utcfromtimestamp_ms(self.start)}, '
                f'end={datetime_utcfromtimestamp_ms(self.end)})')


class SymbolInfo(NamedTuple):
    min_size: Decimal
    max_size: Decimal
    size_step: Decimal
    min_price: Decimal
    max_price: Decimal
    price_step: Decimal


class Advice(Enum):
    LONG = 0
    SHORT = 1


class Side(Enum):
    BUY = 0
    SELL = 1


class OrderType(Enum):
    MARKET = 0
    LIMIT = 1
    STOP_LOSS = 2
    STOP_LOSS_LIMIT = 3
    TAKE_PROFIT = 4
    TAKE_PROFIT_LIMIT = 5
    LIMIT_MAKER = 6


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


class OrderResult(NamedTuple):
    status: OrderResultStatus
    fills: Fills

    @staticmethod
    def not_placed() -> OrderResult:
        return OrderResult(
            status=OrderResultStatus.NOT_PLACED,
            fills=Fills())


class OrderResultStatus(Enum):
    NOT_PLACED = 0
    FILLED = 1
