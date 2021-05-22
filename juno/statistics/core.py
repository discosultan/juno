from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from juno import Interval, Timestamp
from juno.assets import Fees, Filters
from juno.candles import Candle
from juno.math import annualized, round_half_up
from juno.trading import CloseReason, Position, TradingSummary


@dataclass
class CoreStatistics:
    start: Timestamp
    end: Timestamp
    duration: Interval
    cost: Decimal
    gain: Decimal
    profit: Decimal
    roi: Decimal
    annualized_roi: Decimal
    mean_position_profit: Decimal
    mean_long_position_profit: Decimal
    mean_short_position_profit: Decimal
    mean_position_duration: Interval
    mean_long_position_duration: Interval
    mean_short_position_duration: Interval
    max_drawdown: Decimal
    mean_drawdown: Decimal
    return_over_max_drawdown: Decimal
    num_positions: int
    num_positions_in_profit: int
    num_positions_in_loss: int
    num_long_positions: int
    num_long_positions_in_profit: int
    num_long_positions_in_loss: int
    num_short_positions: int
    num_short_positions_in_profit: int
    num_short_positions_in_loss: int
    num_stop_losses: int
    num_take_profits: int

    @staticmethod
    def compose(summary: TradingSummary) -> CoreStatistics:
        start = summary.start
        end = summary.end
        duration = end - start
        positions = list(summary.get_positions())
        long_positions = [p for p in positions if isinstance(p, Position.Long)]
        short_positions = [p for p in positions if isinstance(p, Position.Short)]
        profit = summary.profit
        cost = summary.quote
        roi = profit / cost

        # Drawdowns.
        quote = summary.quote
        max_quote = quote
        max_drawdown = Decimal('0.0')
        sum_drawdown = Decimal('0.0')
        # drawdowns = []
        for pos in positions:
            quote += pos.profit
            max_quote = max(max_quote, quote)
            drawdown = Decimal('1.0') - quote / max_quote
            # drawdowns.append(drawdown)
            sum_drawdown += drawdown
            max_drawdown = max(max_drawdown, drawdown)
        mean_drawdown = Decimal('0.0') if len(positions) == 0 else sum_drawdown / len(positions)

        return CoreStatistics(
            start=start,
            end=end,
            cost=cost,
            gain=cost + profit,
            profit=profit,
            roi=roi,
            annualized_roi=annualized(duration, roi),
            duration=duration,
            num_positions=len(positions),
            num_long_positions=len(long_positions),
            num_short_positions=len(short_positions),
            num_positions_in_profit=CoreStatistics._num_positions_in_profit(positions),
            num_long_positions_in_profit=CoreStatistics._num_positions_in_profit(long_positions),
            num_short_positions_in_profit=CoreStatistics._num_positions_in_profit(short_positions),
            num_positions_in_loss=CoreStatistics._num_positions_in_loss(positions),
            num_long_positions_in_loss=CoreStatistics._num_positions_in_loss(long_positions),
            num_short_positions_in_loss=CoreStatistics._num_positions_in_loss(short_positions),
            num_stop_losses=sum(1 for p in positions if p.close_reason is CloseReason.STOP_LOSS),
            num_take_profits=sum(
                1 for p in positions if p.close_reason is CloseReason.TAKE_PROFIT
            ),
            mean_position_duration=CoreStatistics._mean_position_duration(positions),
            mean_long_position_duration=CoreStatistics._mean_position_duration(long_positions),
            mean_short_position_duration=CoreStatistics._mean_position_duration(short_positions),
            mean_position_profit=CoreStatistics._mean_position_profit(positions),
            mean_long_position_profit=CoreStatistics._mean_position_profit(long_positions),
            mean_short_position_profit=CoreStatistics._mean_position_profit(short_positions),
            max_drawdown=max_drawdown,
            mean_drawdown=mean_drawdown,
            return_over_max_drawdown=Decimal('0.0') if max_drawdown == 0 else roi / max_drawdown,
        )

    @staticmethod
    def _num_positions_in_profit(positions: Sequence[Position.Closed]) -> int:
        return sum(1 for p in positions if p.profit >= 0)

    @staticmethod
    def _num_positions_in_loss(positions: Sequence[Position.Closed]) -> int:
        return sum(1 for p in positions if p.profit < 0)

    @staticmethod
    def _mean_position_profit(positions: Sequence[Position.Closed]) -> Decimal:
        if len(positions) == 0:
            return Decimal('0.0')
        return statistics.mean(x.profit for x in positions)

    @staticmethod
    def _mean_position_duration(positions: Sequence[Position.Closed]) -> Interval:
        if len(positions) == 0:
            return 0
        return int(statistics.mean(x.duration for x in positions))

    @staticmethod
    def calculate_hodl_profit(
        summary: TradingSummary, fees: Fees, filters: Filters, first_candle: Candle,
        last_candle: Candle
    ) -> Decimal:
        base_hodl = filters.size.round_down(summary.quote / first_candle.close)
        base_hodl -= round_half_up(base_hodl * fees.taker, filters.base_precision)
        quote_hodl = filters.size.round_down(base_hodl) * last_candle.close
        quote_hodl -= round_half_up(quote_hodl * fees.taker, filters.quote_precision)
        return quote_hodl - summary.quote
