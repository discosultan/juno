import logging
from decimal import Decimal
from typing import Any, Dict, Tuple

from juno import SymbolInfo
from juno.components import Informant
from juno.math import adjust_size
from juno.strategies import new_strategy
from juno.utils import EventEmitter

from .summary import Position, TradingSummary

_log = logging.getLogger(__name__)


class Backtest:

    required_components = ['informant']

    def __init__(self, components: Dict[str, Any]) -> None:
        self._informant: Informant = components['informant']
        self.event = EventEmitter()

    async def run(self, exchange: str, symbol: str, interval: int, start: int, end: int,
                  quote: Decimal, strategy_config: Dict[str, Any],
                  restart_on_missed_candle: bool = True) -> TradingSummary:
        _log.info('running backtest')

        assert end > start
        assert quote > 0

        fees = self._informant.get_fees(exchange)
        symbol_info = self._informant.get_symbol_info(exchange, symbol)
        summary = TradingSummary(exchange, symbol, interval, start, end, quote, fees, symbol_info)
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

            async for candle, primary in self._informant.stream_candles(
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
                    if size == 0:
                        _log.warning(f'quote balance too low to open a position; stopping')
                        break
                    open_position = Position(candle.time, size, candle.close, fee)
                elif open_position and advice == -1:
                    size, fee, quote = _calc_sell_base_fee_quote(
                        open_position.base_size - open_position.base_fee, candle.close, fees.taker,
                        symbol_info)
                    open_position.close(candle.time, size, candle.close, fee)
                    summary.append_position(open_position)
                    open_position = None

            if not restart:
                break

        if last_candle is not None and open_position:
            size, fee, quote = _calc_sell_base_fee_quote(
                open_position.base_size - open_position.base_fee, candle.close, fees.taker,
                symbol_info)
            open_position.close(last_candle.time, size, last_candle.close, fee)
            summary.append_position(open_position)
            open_position = None

        _log.info('backtest finished')
        return summary


def _calc_buy_base_fee_quote(quote: Decimal, price: Decimal, fee_rate: Decimal,
                             sinfo: SymbolInfo) -> Tuple[Decimal, Decimal, Decimal]:
    size = quote / price
    size = adjust_size(size, sinfo.min_size, sinfo.max_size, sinfo.size_step)
    return size, size * fee_rate, quote - size * price


def _calc_sell_base_fee_quote(base: Decimal, price: Decimal, fee_rate: Decimal,
                              sinfo: SymbolInfo) -> Tuple[Decimal, Decimal, Decimal]:
    size = adjust_size(base, sinfo.min_size, sinfo.max_size, sinfo.size_step)
    quote = size * price
    return size, quote * fee_rate, quote
