import asyncio
from decimal import Decimal
import logging
import statistics

import numpy as np

from juno.math import ceil_multiple
from juno.strategies import new_strategy


_log = logging.getLogger(__name__)


class Backtest:

    required_components = ['informant']

    def __init__(self, components: dict) -> None:
        self.informant = components['informant']

    async def run(self, exchange: str, symbol: str, start: int, end: int, interval: int,
                  strategy_config: dict):
        _log.info('running backtest')

        symbol_info = self.informant.get_symbol_info(exchange, symbol)
        summary = TradingSummary()
        open_position = None
        last_candle = None

        async def trade():
            nonlocal start, last_candle
            restart = False

            strategy = new_strategy(strategy_config)
            # Adjust start to accommodate for the required history before a strategy becomes
            # effective.
            start -= strategy.req_history

            async for candle, primary in self.informant.stream_candles(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                    start=start,
                    end=end):
                if not primary:
                    continue

                summary.append_candle(candle)

                # If we have missed a candle, reset and start over.
                if candle.time - last_candle.time >= interval * 2:
                    _log.error(f'missed candle(s); last candle {last_candle}; current candle '
                            f'{candle}; resetting strategy')
                    start = candle.time
                    restart = True

                advice = strategy.update(candle)

                if open_position is None and advice == 1:
                    open_position = Position(candle.time, )

                last_candle = candle
                if restart:
                    return True
        
            return False

        while True:
            restart = await trade()
            if restart:
                continue
            else:
                break

        if last_candle is not None:
            await broker.advice(last_candle.time, final_advice)
            await ee.emit('summary', summary)

        _log.info('backtest finished')


# TODO: Add support for external token fees (i.e BNB)
class Position:

    def __init__(self, time: int, size: Decimal, price: Decimal, fee: Decimal) -> None:
        self.time = time
        self.size = size
        self.price = price
        self.fee = fee

    def close(self, time: int, size: Decimal, price: Decimal, fee: Decimal) -> None:
        self.closing_time = time
        self.closing_size = size
        self.closing_price = price
        self.closing_fee = fee

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
        return self.size * self.price

    @property
    def gain(self) -> Decimal:
        return (self.closing_size - self.closing_size * self.closing_fee) * self.closing_price

    @property
    def dust(self) -> Decimal:
        self._ensure_closed()
        return self.size - self.closing_size

    def _ensure_closed(self) -> None:
        if not self.closing_price:
            raise ValueError('position not closed')


class TradingSummary:

    def __init__(self):
        self.positions = []
        self.first_candle = None
        self.last_candle = None

    def append_candle(self, candle):
        if self.first_candle is None:
            self.first_candle = candle
        self.last_candle = candle

    def append_position(self, pos):
        self.positions.append(pos)

    def __repr__(self):
        return f'{self.__class__.__name__} {self.__dict__}'

    @property
    def total_profit(self) -> Decimal:
        return sum((p.profit for p in self.positions))

    # @property
    # def total_hodl_profit(self):
    #     base_hodl = self.acc_info.quote_balance / self.first_candle.close
    #     base_hodl -= base_hodl * self.acc_info.fees.taker
    #     quote_hodl = base_hodl * self.last_candle.close
    #     quote_hodl -= quote_hodl * self.acc_info.fees.taker
    #     return quote_hodl - self.acc_info.quote_balance

    @property
    def total_duration(self) -> int:
        # TODO: Do we want to add interval?
        return self.last_candle.time - self.first_candle.time

    # @property
    # def yearly_roi(self):
    #     yearly_profit = self.total_profit * MS_IN_YEAR / self.total_duration
    #     return yearly_profit / self.acc_info.quote_balance

    # @property
    # def max_drawdown(self):
    #     return np.max(self._drawdowns)

    # @property
    # def mean_drawdown(self):
    #     return np.mean(self._drawdowns)

    @property
    def mean_position_profit(self) -> Decimal:
        if len(self.positions) == 0:
            return Decimal(0)
        return statistics.mean((x.profit for x in self.positions))

    @property
    def mean_position_duration(self) -> int:
        if len(self.positions) == 0:
            return 0
        return int(statistics.mean([x.duration for x in self.positions]))

    @property
    def start(self) -> int:
        return 0 if self.first_candle is None else self.first_candle.time

    @property
    def end(self) -> int:
        # TODO: Do we want to add interval?
        return 0 if self.last_candle is None else self.last_candle.time

    # @property
    # def _drawdowns(self):
    #     quote = self.acc_info.quote_balance
    #     if self.acc_info.base_balance > self.ap_info.min_qty:
    #         base_to_quote = self.acc_info.base_balance
    #         base_to_quote -= base_to_quote % self.ap_info.qty_step_size
    #         quote += base_to_quote * self.first_candle.close

    #     quote_history = [quote]
    #     for pos in self.closed_positions:
    #         quote += pos.profit
    #         quote_history.append(quote)

    #     # Ref: https://discuss.pytorch.org/t/efficiently-computing-max-drawdown/6480
    #     xs = np.array(quote_history)
    #     maximums = np.maximum.accumulate(xs)
    #     return 1.0 - xs / maximums
