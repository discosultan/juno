import itertools
import statistics
from decimal import Decimal
from typing import List, Optional

from juno import Candle, Fees, Fills
from juno.filters import Filters
from juno.time import YEAR_MS, datetime_utcfromtimestamp_ms, strfinterval


# TODO: Add support for external token fees (i.e BNB)
class Position:
    def __init__(self, time: int, fills: Fills) -> None:
        self.time = time
        self.fills = fills
        self.closing_time = 0
        self.closing_fills: Optional[Fills] = None

    def __str__(self) -> str:
        res = (
            f'Start: {datetime_utcfromtimestamp_ms(self.start)}'
            f'\nCost: {self.cost}'
            f'\nBase fee: {self.fills.total_fee}'
            '\n'
        )
        for i, fill in enumerate(self.fills, 1):
            res += f'\nTrade {i}: (price: {fill.price}, size: {fill.size})'
        if self.closing_fills:
            res += (
                f'\nGain: {self.gain}'
                f'\nProfit: {self.profit}'
                f'\nROI: {self.roi:.0%}'
                f'\nAnnualized ROI: {self.annualized_roi:.0%}'
                f'\nDust: {self.dust}'
                f'\nQuote fee: {self.closing_fills.total_fee}'
                f'\nEnd: {datetime_utcfromtimestamp_ms(self.end)}'
                f'\nDuration: {strfinterval(self.duration)}'
                '\n'
            )
            for i, fill in enumerate(self.closing_fills, 1):
                res += f'\nTrade {i}: (price: {fill.price}, size: {fill.size})'
        return res

    def close(self, time: int, fills: Fills) -> None:
        assert fills.total_size <= self.fills.total_size - self.fills.total_fee

        self.closing_time = time
        self.closing_fills = fills

    @property
    def total_size(self) -> Decimal:
        return self.fills.total_size

    @property
    def start(self) -> int:
        return self.time

    @property
    def cost(self) -> Decimal:
        return self.fills.total_quote

    @property
    def gain(self) -> Decimal:
        assert self.closing_fills
        return self.closing_fills.total_quote - self.closing_fills.total_fee

    @property
    def profit(self) -> Decimal:
        assert self.closing_fills
        return self.gain - self.cost

    @property
    def roi(self) -> Decimal:
        assert self.closing_fills
        return self.profit / self.cost

    # Ref: https://www.investopedia.com/articles/basics/10/guide-to-calculating-roi.asp
    @property
    def annualized_roi(self) -> Decimal:
        assert self.closing_fills
        n = Decimal(self.duration) / YEAR_MS
        return (1 + self.roi)**(1 / n) - 1

    @property
    def dust(self) -> Decimal:
        assert self.closing_fills
        return self.fills.total_size - self.fills.total_fee - self.closing_fills.total_size

    @property
    def end(self) -> int:
        assert self.closing_fills
        return self.closing_time

    @property
    def duration(self) -> int:
        assert self.closing_fills
        return self.closing_time - self.time


# TODO: both positions and candles could theoretically grow infinitely
class TradingSummary:
    def __init__(
        self, interval: int, start: int, quote: Decimal, fees: Fees, filters: Filters
    ) -> None:
        self.interval = interval
        self.start = start
        self.quote = quote
        self.fees = fees
        self.filters = filters

        # self.candles: List[Candle] = []
        self.positions: List[Position] = []
        self.first_candle: Optional[Candle] = None
        self.last_candle: Optional[Candle] = None

        self._drawdowns_dirty = True
        self._drawdowns: List[Decimal] = []

    def append_candle(self, candle: Candle) -> None:
        # self.candles.append(candle)
        if not self.first_candle:
            self.first_candle = candle
        self.last_candle = candle

    def append_position(self, pos: Position) -> None:
        self.positions.append(pos)
        self._drawdowns_dirty = True

    def __str__(self) -> str:
        return (
            f'{datetime_utcfromtimestamp_ms(self.start)} - '
            f'{datetime_utcfromtimestamp_ms(self.end)}\n'
            f'Cost: {self.cost}\n'
            f'Gain: {self.gain}\n'
            f'Profit: {self.profit}\n'
            f'Potential hodl profit: {self.potential_hodl_profit}\n'
            f'ROI: {self.roi:.0%}\n'
            f'Annualized ROI: {self.annualized_roi:.0%}\n'
            f'Duration: {strfinterval(self.duration)}\n'
            f'Between: {datetime_utcfromtimestamp_ms(self.start)} - '
            f'{datetime_utcfromtimestamp_ms(self.end)}\n'
            f'Max drawdown: {self.max_drawdown:.0%}\n'
            f'Mean drawdown: {self.mean_drawdown:.0%}\n'
            f'Positions taken: {len(self.positions)}\n'
            f'Mean profit per position: {self.mean_position_profit}\n'
            f'Mean duration per position: {strfinterval(self.mean_position_duration)}'
        )

    def __repr__(self) -> str:
        return f'{type(self).__name__} {self.__dict__}'

    @property
    def end(self) -> int:
        if self.last_candle:
            return self.last_candle.time + self.interval
        return 0

    @property
    def cost(self) -> Decimal:
        return self.quote

    @property
    def gain(self) -> Decimal:
        return self.quote + self.profit

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self.positions), Decimal(0))

    @property
    def roi(self) -> Decimal:
        return self.profit / self.cost

    @property
    def annualized_roi(self) -> Decimal:
        n = Decimal(self.duration) / YEAR_MS
        if n == 0:
            return Decimal(0)
        return (1 + self.roi)**(1 / n) - 1

    @property
    def potential_hodl_profit(self) -> Decimal:
        if not self.first_candle or not self.last_candle:
            return Decimal(0)
        base_hodl = self.quote / self.first_candle.close
        base_hodl -= base_hodl * self.fees.taker
        quote_hodl = base_hodl * self.last_candle.close
        quote_hodl -= quote_hodl * self.fees.taker
        return quote_hodl - self.quote

    @property
    def duration(self) -> int:
        return self.end - self.start if self.end > 0 else 0

    @property
    def mean_position_profit(self) -> Decimal:
        if len(self.positions) == 0:
            return Decimal(0)
        return statistics.mean((x.profit for x in self.positions))

    @property
    def mean_position_duration(self) -> int:
        if len(self.positions) == 0:
            return 0
        return int(statistics.mean((x.duration for x in self.positions)))

    # TODO: Optimize drawdown related data calculation. Single iteration please!
    @property
    def drawdowns(self) -> List[Decimal]:
        if self._drawdowns_dirty:
            quote = self.quote

            # TODO: Probably not needed? We currently assume start end ending with empty base
            #       balance (excluding dust).
            # if self.acc_info.base_balance > self.ap_info.min_qty:
            #     base_to_quote = self.acc_info.base_balance
            #     base_to_quote -= base_to_quote % self.ap_info.qty_step_size
            #     quote += base_to_quote * self.first_candle.close

            quote_history = [quote]
            for pos in self.positions:
                quote += pos.profit
                quote_history.append(quote)

            # Ref: https://discuss.pytorch.org/t/efficiently-computing-max-drawdown/6480
            maximums = itertools.accumulate(quote_history, max)

            self._drawdowns = [Decimal(1) - (a / b) for a, b in zip(quote_history, maximums)]
            self._drawdowns_dirty = False

        return self._drawdowns

    @property
    def max_drawdown(self) -> Decimal:
        if len(self.positions) == 0:
            return Decimal(0)
        return max(self.drawdowns)

    @property
    def mean_drawdown(self) -> Decimal:
        if len(self.positions) == 0:
            return Decimal(0)
        return statistics.mean(self.drawdowns)


class TradingContext:
    def __init__(self, quote: Decimal) -> None:
        self.quote = quote
        self.open_position: Optional[Position] = None
