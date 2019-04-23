import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from juno import Candle
from juno.components import Informant, Orderbook
from juno.math import floor_multiple
from juno.strategies import new_strategy
from juno.time import time_ms

from .agent import Agent
from .summary import Position, TradingSummary

_log = logging.getLogger(__name__)


class Paper(Agent):

    required_components = ['informant', 'orderbook']
    open_position: Optional[Position]

    async def run(self, exchange: str, symbol: str, interval: int, end: int, quote: Decimal,
                  strategy_config: Dict[str, Any], restart_on_missed_candle: bool = True,
                  get_time: Optional[Callable[[], int]] = None) -> TradingSummary:
        if not get_time:
            get_time = time_ms

        now = floor_multiple(get_time(), interval)
        assert end > now
        assert quote > 0

        self.exchange = exchange
        self.symbol = symbol
        self.quote = quote

        informant: Informant = self.components['informant']
        self.orderbook: Orderbook = self.components['orderbook']

        self.fees = informant.get_fees(exchange)
        _log.info(f'Fees: {self.fees}')

        self.symbol_info = informant.get_symbol_info(exchange, symbol)
        _log.info(f'Symbol info: {self.symbol_info}')

        self.summary = TradingSummary(exchange, symbol, interval, now, end, quote, self.fees,
                                      self.symbol_info)
        self.open_position = None
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
                start = now - strategy.req_history * interval

            async for candle, primary in informant.stream_candles(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                    start=start,
                    end=end):
                if not primary:
                    continue

                self.summary.append_candle(candle)

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

                if not self.open_position and advice == 1:
                    if not self._try_open_position(candle):
                        _log.warning(f'quote balance too low to open a position; stopping')
                        break
                elif self.open_position and advice == -1:
                    self._close_position(candle)

            if not restart:
                break

        if last_candle is not None and self.open_position:
            self._close_position(last_candle)

        return self.summary

    def _try_open_position(self, candle: Candle) -> bool:
        size = self.orderbook.find_market_order_buy_size(self.exchange, self.symbol, self.quote,
                                                         self.symbol_info.size_step)

        # size = self.quote / candle.close
        # size = adjust_size(size, self.symbol_info.min_size, self.symbol_info.max_size,
        #                    self.symbol_info.size_step)

        if size == 0:
            return False

        self.open_position = Position(candle.time, size, candle.close, size * self.fees.taker)
        self.quote -= size * candle.close

        return True

    def _close_position(self, candle: Candle) -> None:
        assert self.open_position

        base = self.open_position.base_size - self.open_position.base_fee
        size = self.orderbook.find_market_order_sell_size(self.exchange, self.symbol, base,
                                                          self.symbol_info.size_step)
        quote = size * candle.close
        fees = quote * self.fees.taker

        self.open_position.close(candle.time, size, candle.close, fees)
        self.summary.append_position(self.open_position)
        self.open_position = None
        self.quote = quote - fees
