import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from juno import (
    Advice, Candle, Fill, Fills, Position, TradingContext, TradingSummary
)
from juno.components import Informant
from juno.math import floor_multiple, round_half_up
from juno.strategies import new_strategy
from juno.time import time_ms
from juno.utils import unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Backtest(Agent):
    def __init__(self, informant: Informant) -> None:
        super().__init__()
        self.informant = informant

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        quote: Decimal,
        strategy_config: Dict[str, Any],
        end: Optional[int] = None,
        restart_on_missed_candle: bool = False,
    ) -> None:
        now = time_ms()

        if end is None:
            end = floor_multiple(now, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        self.base_asset, self.quote_asset = unpack_symbol(symbol)

        self.fees = self.informant.get_fees(exchange, symbol)
        self.filters = self.informant.get_filters(exchange, symbol)

        self.ctx = TradingContext(quote)
        self.result = TradingSummary(
            interval=interval, start=start, quote=quote, fees=self.fees, filters=self.filters
        )
        restart_count = 0

        while True:
            self.last_candle = None
            restart = False

            strategy = new_strategy(strategy_config)

            if restart_count == 0:
                # Adjust start to accommodate for the required history before a strategy becomes
                # effective. Only do it on first run because subsequent runs mean missed candles
                # and we don't want to fetch passed a missed candle.
                _log.info(
                    f'fetching {strategy.req_history} candle(s) before start time to '
                    'warm-up strategy'
                )
                start -= strategy.req_history * interval

            async for candle in self.informant.stream_candles(
                exchange=exchange, symbol=symbol, interval=interval, start=start, end=end
            ):
                self.result.append_candle(candle)

                # Check if we have missed a candle.
                if self.last_candle and candle.time - self.last_candle.time >= interval * 2:
                    _log.warning(
                        f'missed candle(s); last candle {self.last_candle}; current '
                        f'candle {candle}'
                    )
                    if restart_on_missed_candle:
                        _log.info('restarting strategy')
                        start = candle.time
                        restart = True
                        restart_count += 1
                        break

                self.last_candle = candle
                advice = strategy.update(candle)

                if not self.ctx.open_position and advice is Advice.BUY:
                    if not self._try_open_position(candle):
                        _log.warning(f'quote balance too low to open a position; stopping')
                        break
                elif self.ctx.open_position and advice is Advice.SELL:
                    self._close_position(candle)

            if not restart:
                break

    async def finalize(self) -> None:
        if self.last_candle and self.ctx.open_position:
            _log.info('closing currently open position')
            self._close_position(self.last_candle)

    def _try_open_position(self, candle: Candle) -> Optional[Position]:
        price = candle.close

        size = self.filters.size.round_down(self.ctx.quote / price)
        if size == 0:
            return None

        fee = round_half_up(size * self.fees.taker, self.filters.base_precision)

        self.ctx.open_position = Position(
            time=candle.time,
            fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.base_asset)])
        )

        self.ctx.quote -= size * price

        return self.ctx.open_position

    def _close_position(self, candle: Candle) -> Position:
        pos = self.ctx.open_position
        assert pos

        price = candle.close
        size = self.filters.size.round_down(pos.total_size - pos.fills.total_fee)

        quote = size * price
        fee = round_half_up(quote * self.fees.taker, self.filters.quote_precision)

        pos.close(
            time=candle.time,
            fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.quote_asset)])
        )
        self.result.append_position(pos)

        self.ctx.quote += quote - fee

        self.ctx.open_position = None
        return pos
