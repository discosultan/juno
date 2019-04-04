import itertools
import statistics
from decimal import Decimal
from typing import List, Optional

from juno import Candle, Fees, SymbolInfo
from juno.time import YEAR_MS, datetime_utcfromtimestamp_ms, strfinterval


# TODO: Add support for external token fees (i.e BNB)
class Position:

    def __init__(self, time: int, base_size: Decimal, quote_price: Decimal, base_fee: Decimal
                 ) -> None:
        self.time = time
        self.base_size = base_size
        self.quote_price = quote_price
        self.base_fee = base_fee

    def __str__(self) -> str:
        return (f'Profit: {self.profit}\n'
                f'ROI: {self.roi}\n'
                f'Duration: {strfinterval(self.duration)}\n'
                f'Between: {datetime_utcfromtimestamp_ms(self.start)} - '
                f'{datetime_utcfromtimestamp_ms(self.end)}')

    def close(self, time: int, base_size: Decimal, quote_price: Decimal, quote_fee: Decimal
              ) -> None:
        print(base_size, self.base_size, self.base_fee)
        assert base_size <= self.base_size - self.base_fee

        self.closing_time = time
        self.closing_base_size = base_size
        self.closing_quote_price = quote_price
        self.closing_quote_fee = quote_fee

    @property
    def duration(self) -> int:
        self._ensure_closed()
        return self.closing_time - self.time

    @property
    def profit(self) -> Decimal:
        self._ensure_closed()
        return self.gain - self.cost

    @property
    def roi(self) -> Decimal:
        self._ensure_closed()
        return self.profit / self.cost

    @property
    def cost(self) -> Decimal:
        return self.base_size * self.quote_price

    @property
    def gain(self) -> Decimal:
        return self.closing_base_size * self.closing_quote_price - self.closing_quote_fee

    @property
    def dust(self) -> Decimal:
        self._ensure_closed()
        return self.base_size - self.base_fee - self.closing_base_size

    @property
    def start(self) -> int:
        return self.time

    @property
    def end(self) -> int:
        self._ensure_closed()
        return self.closing_time

    def _ensure_closed(self) -> None:
        if not self.closing_quote_price:
            raise ValueError('Position not closed')


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

        self.positions: List[Position] = []
        self.first_candle: Optional[Candle] = None
        self.last_candle: Optional[Candle] = None

    def append_candle(self, candle: Candle) -> None:
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
        # TODO: (excluding dust).
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
