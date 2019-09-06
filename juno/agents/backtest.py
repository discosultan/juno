import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from juno import Advice
from juno.components import Informant
from juno.math import floor_multiple
from juno.strategies import new_strategy
from juno.time import time_ms
from juno.trading import TradingContext, close_position, try_open_position

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

        self.fees = self.informant.get_fees(exchange, symbol)
        self.filters = self.informant.get_filters(exchange, symbol)

        self.ctx = TradingContext(
            symbol=symbol,
            interval=interval,
            start=start,
            quote=quote,
            fees=self.fees)
        self.result = self.ctx.summary
        restart_count = 0

        while True:
            self.last_candle = None
            restart = False

            strategy = new_strategy(strategy_config)

            # TODO: candle_start

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
                if not candle.closed:
                    continue

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
                    if not try_open_position(
                        ctx=self.ctx,
                        fees=self.fees,
                        filters=self.filters,
                        candle=candle
                    ):
                        _log.warning(f'quote balance too low to open a position; stopping')
                        break
                elif self.ctx.open_position and advice is Advice.SELL:
                    close_position(
                        ctx=self.ctx,
                        fees=self.fees,
                        filters=self.filters,
                        candle=candle
                    )

            if not restart:
                break

    async def finalize(self) -> None:
        if self.last_candle and self.ctx.open_position:
            _log.info('closing currently open position')
            close_position(
                ctx=self.ctx,
                fees=self.fees,
                filters=self.filters,
                candle=self.last_candle
            )
