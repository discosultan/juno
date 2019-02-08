import asyncio
import logging

from juno.engine import Engine
from juno.math import ceil_multiple
from juno.strategies import new_strategy


_log = logging.getLogger(__name__)


async def backtest(components, config):
    _log.info('running backtest')

    start = config['start']
    interval = config['interval']
    last_candle = None

    async def trade():
        nonlocal start, last_candle

        strategy = new_strategy(**config['strategy'])
        # Adjust start to accommodate for the required history before a strategy becomes
        # effective.
        start -= strategy.req_history

        async for candle, primary in components['informant'].stream_candles(
                exchange=config['exchange'],
                symbol=config['symbol'],
                interval=interval,
                start=start,
                end=config['end']):
            if not primary:
                continue

            # If we have missed a candle, reset and start over.
            if candle.time - last_candle.time >= interval * 2:
                _log.error(f'missed candle(s); last candle {last_candle}; current candle '
                            f'{candle}; resetting strategy')
                start = candle.time
                return True

            advice = strategy.update(candle)

            if advice is not None:

                await broker.advice(candle.time, advice)
                await ee.emit('summary', summary)

            last_candle = candle

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



class TradingSummary:

    def __init__(self)
        self.strategy_name = strategy_name
        self.interval = interval
        self.ap_info = ap_info
        self.acc_info = acc_info

        self.dirty = _Dirty.ALL

        self.base_balance = acc_info.base_balance
        self.quote_balance = acc_info.quote_balance

        self.first_candle, self.last_candle = None, None
        self.closed_positions = []

        self.result_cache = {}

        @ee.on('candle')
        async def on_candle(candle, primary):
            if not primary:
                return
            if self.first_candle is None:
                self.first_candle = candle
            self.last_candle = candle
            self.dirty = _Dirty.ALL

        @ee.on('pos_opened')
        async def on_position_opened(pos):
            self.base_balance += pos.open_base_change
            self.quote_balance += pos.open_quote_change
            self.dirty = _Dirty.ALL

        @ee.on('pos_closed')
        async def on_position_closed(pos):
            self.base_balance += pos.close_base_change
            self.quote_balance += pos.close_quote_change
            self.closed_positions.append(pos)
            self.dirty = _Dirty.ALL

    def __repr__(self):
        return f'{self.__class__.__name__} {self.__dict__}'

    @property
    def total_profit(self):
        def calc():
            quote_from_base = self.base_balance * self.last_candle.close
            quote_from_base -= quote_from_base * self.acc_info.fees.taker
            return self.quote_balance + quote_from_base - self.acc_info.quote_balance
        return self._calc(_Dirty.TOTAL_PROFIT, calc, 0.0)

    @property
    def total_hodl_profit(self):
        def calc():
            base_hodl = self.acc_info.quote_balance / self.first_candle.close
            base_hodl -= base_hodl * self.acc_info.fees.taker
            quote_hodl = base_hodl * self.last_candle.close
            quote_hodl -= quote_hodl * self.acc_info.fees.taker
            return quote_hodl - self.acc_info.quote_balance
        return self._calc(_Dirty.TOTAL_HODL_PROFIT, calc, 0.0)

    @property
    def total_duration(self):
        def calc():
            return self.last_candle.time - self.first_candle.time + self.interval
        return self._calc(_Dirty.TOTAL_DURATION, calc, 0)

    @property
    def yearly_roi(self):
        def calc():
            yearly_profit = self.total_profit * MS_IN_YEAR / self.total_duration
            return yearly_profit / self.acc_info.quote_balance
        return self._calc(_Dirty.YEARLY_ROI, calc, 0.0)

    @property
    def max_drawdown(self):
        def calc():
            return np.max(self._drawdowns)
        return self._calc(_Dirty.MAX_DRAWDOWN, calc, 0.0)

    @property
    def mean_drawdown(self):
        def calc():
            return np.mean(self._drawdowns)
        return self._calc(_Dirty.MEAN_DRAWDOWN, calc, 0.0)

    @property
    def mean_position_profit(self):
        def calc():
            if len(self.closed_positions) == 0:
                return 0.0
            return statistics.mean([x.profit for x in self.closed_positions])
        return self._calc(_Dirty.MEAN_TRADE_PROFIT, calc, 0.0)

    @property
    def mean_position_duration(self):
        def calc():
            if len(self.closed_positions) == 0:
                return 0
            return int(statistics.mean([x.duration for x in self.closed_positions]))
        return self._calc(_Dirty.MEAN_TRADE_DURATION, calc, 0)

    @property
    def start(self):
        return 0 if self.first_candle is None else self.first_candle.time

    @property
    def end(self):
        return 0 if self.last_candle is None else self.last_candle.time + self.interval

    @property
    def _drawdowns(self):
        def calc():
            quote = self.acc_info.quote_balance
            if self.acc_info.base_balance > self.ap_info.min_qty:
                base_to_quote = self.acc_info.base_balance
                base_to_quote -= base_to_quote % self.ap_info.qty_step_size
                quote += base_to_quote * self.first_candle.close

            quote_history = [quote]
            for pos in self.closed_positions:
                quote += pos.profit
                quote_history.append(quote)

            # Ref: https://discuss.pytorch.org/t/efficiently-computing-max-drawdown/6480
            xs = np.array(quote_history)
            maximums = np.maximum.accumulate(xs)
            return 1.0 - xs / maximums

        return self._calc(_Dirty.DRAWDOWNS, calc, np.array([0.0]))

    def _calc(self, flag, calc, default):
        if self.dirty & flag:
            self.dirty &= ~flag
            if self.first_candle is None:
                self.result_cache[flag] = default
            else:
                self.result_cache[flag] = calc()
        return self.result_cache[flag]



try:
    asyncio.run(BacktestEngine().main())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
