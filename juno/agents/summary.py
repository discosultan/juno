import itertools
import statistics
from decimal import Decimal
from typing import List, Optional

from juno import Candle, Fees, Fills, SymbolInfo
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
               '\n')
        for i, fill in enumerate(self.fills, 1):
            res += f'\nTrade {i}: (price: {fill.price}, size: {fill.size})'
        if self.closing_fills:
            res += (
                    f'\nGain: {self.gain}'
                    f'\nProfit: {self.profit}'
                    f'\nROI: {self.roi}'
                    f'\nDust: {self.dust}'
                    f'\nQuote fee: {self.closing_fills.total_fee}'
                    f'\nEnd: {datetime_utcfromtimestamp_ms(self.end)}'
                    f'\nDuration: {strfinterval(self.duration)}'
                    '\n')
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
    def profit(self) -> Decimal:
        assert self.closing_fills
        return self.gain - self.cost

    @property
    def roi(self) -> Decimal:
        assert self.closing_fills
        return self.profit / self.cost

    @property
    def gain(self) -> Decimal:
        assert self.closing_fills
        return self.closing_fills.total_quote - self.closing_fills.total_fee

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

    def __init__(self, exchange: str, symbol: str, interval: int, start: int, end: int,
                 quote: Decimal, fees: Fees, symbol_info: SymbolInfo) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.interval = interval
        self.start = start
        self.end = end
        self.quote = quote
        self.fees = fees
        self.symbol_info = symbol_info

        self.candles: List[Candle] = []
        self.positions: List[Position] = []
        self.first_candle: Optional[Candle] = None
        self.last_candle: Optional[Candle] = None

    def append_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
        if self.first_candle is None:
            self.first_candle = candle
        self.last_candle = candle

    def append_position(self, pos: Position) -> None:
        self.positions.append(pos)

    def __str__(self) -> str:
        return (f'{self.exchange} {self.symbol} {strfinterval(self.interval)} '
                f'{datetime_utcfromtimestamp_ms(self.start)} - '
                f'{datetime_utcfromtimestamp_ms(self.end)}\n'
                f'Start balance: {self.start_balance}\n'
                f'End balance: {self.end_balance}\n'
                f'Total profit: {self.profit}\n'
                f'Potential hodl profit: {self.potential_hodl_profit}\n'
                f'Total duration: {strfinterval(self.duration)}\n'
                f'Between: {datetime_utcfromtimestamp_ms(self.start)} - '
                f'{datetime_utcfromtimestamp_ms(self.end)}\n'
                f'Positions taken: {len(self.positions)}\n'
                f'Mean profit per position: {self.mean_position_profit}\n'
                f'Mean duration per position: {strfinterval(self.mean_position_duration)}')

    def __repr__(self) -> str:
        return f'{type(self).__name__} {self.__dict__}'

    @property
    def start_balance(self) -> Decimal:
        return self.quote

    @property
    def end_balance(self) -> Decimal:
        return self.quote + self.profit

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self.positions))  # type: ignore

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
        # if not self.first_candle or not self.last_candle:
        #     return 0
        # return self.last_candle.time - self.first_candle.time + self.interval
        return self.end - self.start

    @property
    def yearly_roi(self) -> Decimal:
        yearly_profit = self.profit * YEAR_MS / self.duration
        return yearly_profit / self.quote

    @property
    def max_drawdown(self) -> Decimal:
        return max(self._drawdowns)

    @property
    def mean_drawdown(self) -> Decimal:
        return statistics.mean(self._drawdowns)

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

    @property
    def _drawdowns(self) -> List[Decimal]:
        quote = self.quote

        # TODO: Probably not needed? We currently assume start end ending with empty base balance
        #       (excluding dust).
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
        return [Decimal(1) - (a / b) for a, b in zip(quote_history, maximums)]
