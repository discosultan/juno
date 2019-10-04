import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

import juno.json as json
from juno import Advice, Candle, Position, TradingContext, TradingSummary
from juno.brokers import Broker
from juno.components import Chandler, Informant
from juno.math import floor_multiple
from juno.strategies import new_strategy
from juno.time import MAX_TIME_MS, time_ms

from .agent import Agent

_log = logging.getLogger(__name__)


class Paper(Agent):
    def __init__(self, chandler: Chandler, informant: Informant, broker: Broker) -> None:
        super().__init__()
        self.chandler = chandler
        self.informant = informant
        self.broker = broker

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        quote: Decimal,
        strategy_config: Dict[str, Any],
        end: int = MAX_TIME_MS,
        restart_on_missed_candle: bool = True,
        get_time: Optional[Callable[[], int]] = None
    ) -> None:
        if not get_time:
            get_time = time_ms

        now = floor_multiple(get_time(), interval)
        assert end > now

        fees = self.informant.get_fees(exchange, symbol)
        filters = self.informant.get_filters(exchange, symbol)

        assert quote > filters.price.min

        self.exchange = exchange
        self.symbol = symbol

        self.result = TradingSummary(
            interval=interval, start=now, quote=quote, fees=fees, filters=filters
        )
        self.ctx = TradingContext(quote)
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
                    f'fetching {strategy.req_history} candle(s) before start time to warm-up '
                    'strategy'
                )
                start = now - strategy.req_history * interval

            async for candle in self.chandler.stream_candles(
                exchange=exchange, symbol=symbol, interval=interval, start=start, end=end
            ):
                self.result.append_candle(candle)

                # Check if we have missed a candle.
                if self.last_candle and candle.time - self.last_candle.time >= interval * 2:
                    _log.warning(
                        f'missed candle(s); last candle {self.last_candle}; current candle '
                        f'{candle}'
                    )
                    if restart_on_missed_candle:
                        _log.info('restarting strategy')
                        restart = True
                        restart_count += 1
                        break

                self.last_candle = candle
                advice = strategy.update(candle)

                if not self.ctx.open_position and advice is Advice.BUY:
                    if not await self._try_open_position(candle):
                        _log.warning(f'quote balance too low to open a position; stopping')
                        break
                elif self.ctx.open_position and advice is Advice.SELL:
                    await self._close_position(candle)

            if not restart:
                break

    async def finalize(self) -> None:
        if self.last_candle and self.ctx.open_position:
            _log.info('closing currently open position')
            await self._close_position(self.last_candle)
        _log.info(json.dumps(self.result))

    async def _try_open_position(self, candle: Candle) -> Optional[Position]:
        res = await self.broker.buy(
            exchange=self.exchange, symbol=self.symbol, quote=self.ctx.quote, test=True
        )

        self.ctx.open_position = Position(candle.time, res.fills)
        self.ctx.quote -= res.fills.total_quote

        await self.emit('position_opened', self.ctx.open_position)

        return self.ctx.open_position

    async def _close_position(self, candle: Candle) -> Position:
        pos = self.ctx.open_position
        assert pos

        res = await self.broker.sell(
            exchange=self.exchange,
            symbol=self.symbol,
            base=pos.fills.total_size - pos.fills.total_fee,
            test=True
        )

        pos.close(candle.time, res.fills)
        self.result.append_position(pos)
        self.ctx.quote += res.fills.total_quote - res.fills.total_fee

        await self.emit('position_closed', pos)

        self.ctx.open_position = None
        return pos
