import itertools
import statistics
from abc import ABC, abstractproperty
from dataclasses import dataclass
from decimal import Decimal, Overflow
from enum import IntEnum
from typing import Iterable, List, Optional

from juno import Candle, Fees, Fill, Interval, Timestamp
from juno.filters import Filters
from juno.math import round_half_up
from juno.time import YEAR_MS


class MissedCandlePolicy(IntEnum):
    IGNORE = 0
    RESTART = 1
    LAST = 2


class Position(ABC):
    symbol: str
    open_time: int
    close_time: int

    @abstractproperty
    def cost(self) -> Decimal:
        pass

    @abstractproperty
    def base_gain(self) -> Decimal:
        pass

    @abstractproperty
    def base_cost(self) -> Decimal:
        pass

    @abstractproperty
    def gain(self) -> Decimal:
        pass

    @abstractproperty
    def profit(self) -> Decimal:
        pass

    @abstractproperty
    def duration(self) -> int:
        pass


# TODO: Add support for external token fees (i.e BNB)
# Note that we cannot set the dataclass as frozen because that would break JSON deserialization.
@dataclass
class LongPosition(Position):
    symbol: str
    open_time: Timestamp
    open_fills: List[Fill]
    close_time: Timestamp
    close_fills: List[Fill]

    @property
    def cost(self) -> Decimal:
        return Fill.total_quote(self.open_fills)

    @property
    def base_gain(self) -> Decimal:
        return Fill.total_size(self.open_fills) - Fill.total_fee(self.open_fills)

    @property
    def base_cost(self) -> Decimal:
        return Fill.total_size(self.close_fills)

    @property
    def gain(self) -> Decimal:
        return Fill.total_quote(self.close_fills) - Fill.total_fee(self.close_fills)

    @property
    def profit(self) -> Decimal:
        return self.gain - self.cost

    @property
    def roi(self) -> Decimal:
        return self.profit / self.cost

    @property
    def annualized_roi(self) -> Decimal:
        return _annualized_roi(self.duration, self.roi)

    @property
    def dust(self) -> Decimal:
        return (
            Fill.total_size(self.open_fills)
            - Fill.total_fee(self.open_fills)
            - Fill.total_size(self.close_fills)
        )

    @property
    def duration(self) -> Interval:
        return self.close_time - self.open_time


@dataclass
class OpenLongPosition:
    symbol: str
    time: Timestamp
    fills: List[Fill]

    def close(self, time: Timestamp, fills: List[Fill]) -> LongPosition:
        return LongPosition(
            symbol=self.symbol,
            open_time=self.time,
            open_fills=self.fills,
            close_time=time,
            close_fills=fills,
        )

    @property
    def cost(self) -> Decimal:
        return Fill.total_quote(self.fills)

    @property
    def base_gain(self) -> Decimal:
        return Fill.total_size(self.fills) - Fill.total_fee(self.fills)


@dataclass
class ShortPosition(Position):
    symbol: str
    collateral: Decimal  # quote
    borrowed: Decimal  # base
    open_time: Timestamp
    open_fills: List[Fill]
    close_time: Timestamp
    close_fills: List[Fill]
    interest: Decimal  # base

    @property
    def cost(self) -> Decimal:
        return self.collateral

    @property
    def base_gain(self) -> Decimal:
        return self.borrowed

    @property
    def base_cost(self) -> Decimal:
        return self.borrowed

    @property
    def gain(self) -> Decimal:
        return (
            Fill.total_quote(self.open_fills)
            - Fill.total_fee(self.open_fills)
            + self.collateral
            - Fill.total_quote(self.close_fills)
        )

    @property
    def profit(self) -> Decimal:
        return self.gain - self.cost

    @property
    def roi(self) -> Decimal:
        return self.profit / self.cost

    @property
    def annualized_roi(self) -> Decimal:
        return _annualized_roi(self.duration, self.roi)

    # TODO: implement
    # @property
    # def dust(self) -> Decimal:
    #     return (
    #         Fill.total_size(self.open_fills)
    #         - Fill.total_fee(self.open_fills)
    #         - Fill.total_size(self.close_fills)
    #     )

    @property
    def duration(self) -> Interval:
        return self.close_time - self.open_time


@dataclass
class OpenShortPosition:
    symbol: str
    collateral: Decimal
    borrowed: Decimal
    time: Timestamp
    fills: List[Fill]

    def close(self, interest: Decimal, time: Timestamp, fills: List[Fill]) -> ShortPosition:
        return ShortPosition(
            symbol=self.symbol,
            collateral=self.collateral,
            borrowed=self.borrowed,
            open_time=self.time,
            open_fills=self.fills,
            close_time=time,
            close_fills=fills,
            interest=interest,
        )

    @property
    def cost(self) -> Decimal:
        return self.collateral

    @property
    def base_gain(self) -> Decimal:
        return self.borrowed


# TODO: both positions and candles could theoretically grow infinitely
@dataclass(init=False)
class TradingSummary:
    start: Timestamp
    quote: Decimal

    _long_positions: List[LongPosition]
    _short_positions: List[ShortPosition]
    _drawdowns: List[Decimal]

    # TODO: Should we add +interval like we do for summary? Or rather change summary to exclude
    # +interval. Also needs to be adjusted in Rust code.
    end: Optional[Timestamp] = None

    _drawdowns_dirty: bool = True

    def __init__(self, start: Timestamp, quote: Decimal) -> None:
        self.start = start
        self.quote = quote

        self._long_positions = []
        self._short_positions = []
        self._drawdowns = []

    def append_position(self, pos: Position) -> None:
        if isinstance(pos, LongPosition):
            self._long_positions.append(pos)
        elif isinstance(pos, ShortPosition):
            self._short_positions.append(pos)
        else:
            raise NotImplementedError()
        self._drawdowns_dirty = True

    def get_positions(self) -> Iterable[Position]:
        return sorted(
            itertools.chain(self._long_positions, self._short_positions),
            key=lambda p: p.open_time,
        )

    def get_long_positions(self) -> Iterable[LongPosition]:
        return self._long_positions

    def get_short_positions(self) -> Iterable[ShortPosition]:
        return self._short_positions

    def finish(self, end: Timestamp) -> None:
        if self.end is None:
            self.end = end
        else:
            self.end = max(end, self.end)

    @property
    def cost(self) -> Decimal:
        return self.quote

    @property
    def gain(self) -> Decimal:
        return self.quote + self.profit

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self.get_positions()), Decimal('0.0'))

    @property
    def roi(self) -> Decimal:
        return self.profit / self.cost

    @property
    def annualized_roi(self) -> Decimal:
        return _annualized_roi(self.duration, self.roi)

    @property
    def duration(self) -> Interval:
        return 0 if self.end is None else self.end - self.start

    @property
    def num_positions(self) -> int:
        return len(self._long_positions) + len(self._short_positions)

    @property
    def num_long_positions(self) -> int:
        return len(self._long_positions)

    @property
    def num_short_positions(self) -> int:
        return len(self._short_positions)

    @property
    def num_positions_in_profit(self) -> int:
        return sum(1 for p in self.get_positions() if p.profit >= 0)

    @property
    def num_positions_in_loss(self) -> int:
        return sum(1 for p in self.get_positions() if p.profit < 0)

    @property
    def mean_position_profit(self) -> Decimal:
        if self.num_positions == 0:
            return Decimal('0.0')
        return statistics.mean(x.profit for x in self.get_positions())

    @property
    def mean_position_duration(self) -> Interval:
        if self.num_positions == 0:
            return 0
        return int(statistics.mean(x.duration for x in self.get_positions()))

    # @property
    # def drawdowns(self) -> List[Decimal]:
    #     self._calc_drawdowns_if_stale()
    #     return self._drawdowns

    @property
    def max_drawdown(self) -> Decimal:
        self._calc_drawdowns_if_stale()
        return self._max_drawdown

    @property
    def mean_drawdown(self) -> Decimal:
        self._calc_drawdowns_if_stale()
        return self._mean_drawdown

    def _calc_drawdowns_if_stale(self) -> None:
        if not self._drawdowns_dirty:
            return

        quote = self.quote
        max_quote = quote
        self._max_drawdown = Decimal('0.0')
        sum_drawdown = Decimal('0.0')
        self._drawdowns.clear()
        self._drawdowns.append(Decimal('0.0'))
        for pos in self.get_positions():
            quote += pos.profit
            max_quote = max(max_quote, quote)
            drawdown = Decimal('1.0') - quote / max_quote
            self._drawdowns.append(drawdown)
            sum_drawdown += drawdown
            self._max_drawdown = max(self._max_drawdown, drawdown)
        self._mean_drawdown = sum_drawdown / len(self._drawdowns)

        self._drawdowns_dirty = False

    def calculate_hodl_profit(
        self, first_candle: Candle, last_candle: Candle, fees: Fees, filters: Filters
    ) -> Decimal:
        base_hodl = filters.size.round_down(self.quote / first_candle.close)
        base_hodl -= round_half_up(base_hodl * fees.taker, filters.base_precision)
        quote_hodl = filters.size.round_down(base_hodl) * last_candle.close
        quote_hodl -= round_half_up(quote_hodl * fees.taker, filters.quote_precision)
        return quote_hodl - self.quote


# Ref: https://www.investopedia.com/articles/basics/10/guide-to-calculating-roi.asp
def _annualized_roi(duration: int, roi: Decimal) -> Decimal:
    n = Decimal(duration) / YEAR_MS
    if n == 0:
        return Decimal('0.0')
    try:
        return (1 + roi)**(1 / n) - 1
    except Overflow:
        return Decimal('Inf')
