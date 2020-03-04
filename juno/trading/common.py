import statistics
from dataclasses import dataclass
from decimal import Decimal, Overflow
from enum import IntEnum
from typing import List, Optional

from juno import Candle, Fees, Fill, Interval, Timestamp
from juno.filters import Filters
from juno.math import round_half_up
from juno.time import YEAR_MS


class MissedCandlePolicy(IntEnum):
    IGNORE = 0
    RESTART = 1
    LAST = 2


# TODO: Add support for external token fees (i.e BNB)
@dataclass
class Position:
    symbol: str
    time: Timestamp
    fills: List[Fill]
    closing_time: Optional[Timestamp] = None
    closing_fills: Optional[List[Fill]] = None

    def close(self, time: Timestamp, fills: List[Fill]) -> None:
        assert Fill.total_size(fills) <= self.base_gain

        self.closing_time = time
        self.closing_fills = fills

    @property
    def start(self) -> Timestamp:
        return self.time

    @property
    def cost(self) -> Decimal:
        return Fill.total_quote(self.fills)

    @property
    def base_gain(self) -> Decimal:
        return Fill.total_size(self.fills) - Fill.total_fee(self.fills)

    @property
    def base_cost(self) -> Decimal:
        if not self.closing_fills:
            return Decimal('0.0')
        return Fill.total_size(self.closing_fills)

    @property
    def gain(self) -> Decimal:
        if not self.closing_fills:
            return Decimal('0.0')
        return Fill.total_quote(self.closing_fills) - Fill.total_fee(self.closing_fills)

    @property
    def profit(self) -> Decimal:
        if not self.closing_fills:
            return Decimal('0.0')
        return self.gain - self.cost

    @property
    def roi(self) -> Decimal:
        if not self.closing_fills:
            return Decimal('0.0')
        return self.profit / self.cost

    # Ref: https://www.investopedia.com/articles/basics/10/guide-to-calculating-roi.asp
    @property
    def annualized_roi(self) -> Decimal:
        if not self.closing_fills:
            return Decimal('0.0')
        n = Decimal(self.duration) / YEAR_MS
        try:
            return (1 + self.roi)**(1 / n) - 1
        except Overflow:
            return Decimal('Inf')

    @property
    def dust(self) -> Decimal:
        if not self.closing_fills:
            return Decimal('0.0')
        return (
            Fill.total_size(self.fills)
            - Fill.total_fee(self.fills)
            - Fill.total_size(self.closing_fills)
        )

    @property
    def end(self) -> Timestamp:
        if not self.closing_fills:
            return 0
        return self.closing_time

    @property
    def duration(self) -> Interval:
        if not self.closing_time:
            return 0
        return self.closing_time - self.time


# TODO: both positions and candles could theoretically grow infinitely
@dataclass(init=False)
class TradingSummary:
    start: Timestamp
    quote: Decimal

    positions: List[Position]
    _drawdowns: List[Decimal]

    # TODO: Should we add +interval like we do for summary? Or rather change summary to exclude
    # +interval. Also needs to be adjusted in Rust code.
    end: Optional[Timestamp] = None

    _drawdowns_dirty: bool = True

    def __init__(self, start: Timestamp, quote: Decimal) -> None:
        self.start = start
        self.quote = quote

        self.positions = []
        self._drawdowns = []

    def append_position(self, pos: Position) -> None:
        self.positions.append(pos)
        self._drawdowns_dirty = True

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
        return sum((p.profit for p in self.positions), Decimal('0.0'))

    @property
    def roi(self) -> Decimal:
        return self.profit / self.cost

    @property
    def annualized_roi(self) -> Decimal:
        n = Decimal(self.duration) / YEAR_MS
        if n == 0:
            return Decimal('0.0')
        return (1 + self.roi)**(1 / n) - 1

    @property
    def duration(self) -> Interval:
        return 0 if self.end is None else self.end - self.start

    @property
    def num_positions(self) -> int:
        return len(self.positions)

    @property
    def num_positions_in_profit(self) -> int:
        return sum(1 for p in self.positions if p.profit >= 0)

    @property
    def num_positions_in_loss(self) -> int:
        return sum(1 for p in self.positions if p.profit < 0)

    @property
    def mean_position_profit(self) -> Decimal:
        if len(self.positions) == 0:
            return Decimal('0.0')
        return statistics.mean(x.profit for x in self.positions)

    @property
    def mean_position_duration(self) -> Interval:
        if len(self.positions) == 0:
            return 0
        return int(statistics.mean(x.duration for x in self.positions))

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
        for pos in self.positions:
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
