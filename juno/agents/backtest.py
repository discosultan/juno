from decimal import Decimal
import logging
import statistics
from typing import Any, Dict, Tuple

# import numpy as np

from juno import SymbolInfo
from juno.components import Informant
from juno.math import adjust_size
from juno.strategies import new_strategy
from juno.time import datetime_utcfromtimestamp_ms, strfinterval


_log = logging.getLogger(__name__)


class Backtest:

    required_components = ['informant']

    def __init__(self, components: Dict[str, Any]) -> None:
        self.informant: Informant = components['informant']

    # TODO: allow configuring whether to reset on missed candle
    async def run(self, exchange: str, symbol: str, interval: int, start: int, end: int,
                  quote: Decimal, strategy_config: Dict[str, Any],
                  restart_on_missed_candle: bool = True) -> None:
        _log.info('running backtest')

        assert end > start
        assert quote > 0

        symbol_info = self.informant.get_symbol_info(exchange, symbol)
        fees = self.informant.get_fees(exchange)
        summary = TradingSummary(exchange, symbol, interval, start, end)
        open_position = None
        restart_count = 0

        while True:
            last_candle = None
            restart = False

            strategy = new_strategy(strategy_config)

            if restart_count == 0:
                # Adjust start to accommodate for the required history before a strategy becomes
                # effective. Only do it on first run because subsequent runs mean missed candles
                # and we don't want to fetch passed a missed candle.
                _log.info(f'fetching {strategy.req_history} candles before start time to warm-up '
                          'strategy')
                start -= strategy.req_history * interval

            async for candle, primary in self.informant.stream_candles(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                    start=start,
                    end=end):
                if not primary:
                    continue

                summary.append_candle(candle)

                # Check if we have missed a candle.
                if last_candle and candle.time - last_candle.time >= interval * 2:
                    _log.warning(f'missed candle(s); last candle {last_candle}; current candle '
                                 f'{candle}')
                    if restart_on_missed_candle:
                        _log.info('restarting strategy')
                        start = candle.time
                        restart = True
                        restart_count += 1
                        break

                last_candle = candle
                advice = strategy.update(candle)

                if not open_position and advice == 1:
                    size, fee, quote = _calc_buy_base_fee_quote(quote, candle.close, fees.taker,
                                                                symbol_info)
                    open_position = Position(candle.time, size, candle.close, fee)
                elif open_position and advice == -1:
                    size, fee, quote = _calc_sell_base_fee_quote(
                        open_position.size - open_position.fee, candle.close, fees.taker,
                        symbol_info)
                    open_position.close(candle.time, size, candle.close, fee)
                    summary.append_position(open_position)
                    open_position = None

            if not restart:
                break

        if last_candle is not None and open_position:
            size, fee, quote = _calc_sell_base_fee_quote(
                open_position.size - open_position.fee, candle.close, fees.taker, symbol_info)
            open_position.close(last_candle.time, size, last_candle.close, fee)
            summary.append_position(open_position)
            open_position = None

        _log.info('backtest finished')
        for pos in summary.positions:
            _log.debug(pos)
        _log.info(summary)


def _calc_buy_base_fee_quote(quote: Decimal, price: Decimal, fee: Decimal,
                             symbol_info: SymbolInfo) -> Tuple[Decimal, Decimal, Decimal]:
    size = quote / price
    size = adjust_size(size, symbol_info.min_size, symbol_info.max_size,
                       symbol_info.size_step)
    fee_size = size * fee
    return size, fee_size, quote - size * price


def _calc_sell_base_fee_quote(base: Decimal, price: Decimal, fee: Decimal,
                              symbol_info: SymbolInfo) -> Tuple[Decimal, Decimal, Decimal]:
    size = adjust_size(base, symbol_info.min_size, symbol_info.max_size, symbol_info.size_step)
    fee_size = size * fee
    return size, fee_size, (size - fee_size) * price


# TODO: Add support for external token fees (i.e BNB)
class Position:

    def __init__(self, time: int, size: Decimal, price: Decimal, fee: Decimal) -> None:
        self.time = time
        self.size = size
        self.price = price
        self.fee = fee

    def __str__(self):
        return (f'Profit: {self.profit}\n'
                f'ROI: {self.roi}\n'
                f'Duration: {strfinterval(self.duration)}\n'
                f'Between: {datetime_utcfromtimestamp_ms(self.start)} - '
                f'{datetime_utcfromtimestamp_ms(self.end)}')

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

    @property
    def start(self) -> int:
        return self.time

    @property
    def end(self) -> int:
        self._ensure_closed()
        return self.closing_time

    def _ensure_closed(self) -> None:
        if not self.closing_price:
            raise ValueError('position not closed')


class TradingSummary:

    def __init__(self, exchange, symbol, interval, start, end):
        self.exchange = exchange
        self.symbol = symbol
        self.interval = interval
        self.start = start
        self.end = end

        self.positions = []
        self.first_candle = None
        self.last_candle = None

    def append_candle(self, candle):
        if self.first_candle is None:
            self.first_candle = candle
        self.last_candle = candle

    def append_position(self, pos):
        self.positions.append(pos)

    def __str__(self):
        return (f'{self.exchange} {self.symbol} {strfinterval(self.interval)} '
                f'{datetime_utcfromtimestamp_ms(self.start)} - '
                f'{datetime_utcfromtimestamp_ms(self.end)}\n'
                f'Positions taken: {len(self.positions)}\n'
                f'Total profit: {self.profit}\n'
                f'Total duration: {strfinterval(self.duration)}\n'
                f'Between: {datetime_utcfromtimestamp_ms(self.start)} - '
                f'{datetime_utcfromtimestamp_ms(self.end)}\n'
                f'Mean profit per position: {self.mean_position_profit}\n'
                f'Mean duration per position: {strfinterval(self.mean_position_duration)}')

    def __repr__(self):
        return f'{type(self).__name__} {self.__dict__}'

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self.positions))  # type: ignore

    # @property
    # def total_hodl_profit(self):
    #     base_hodl = self.acc_info.quote_balance / self.first_candle.close
    #     base_hodl -= base_hodl * self.acc_info.fees.taker
    #     quote_hodl = base_hodl * self.last_candle.close
    #     quote_hodl -= quote_hodl * self.acc_info.fees.taker
    #     return quote_hodl - self.acc_info.quote_balance

    @property
    def duration(self) -> int:
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

    # @property
    # def start(self) -> int:
    #     return 0 if self.first_candle is None else self.first_candle.time

    # @property
    # def end(self) -> int:
    #     # TODO: Do we want to add interval?
    #     return 0 if self.last_candle is None else self.last_candle.time

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
