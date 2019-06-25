import logging
from typing import Any, Callable, Dict, Optional

import simplejson as json

from juno import Candle, OrderStatus
from juno.brokers import Broker
from juno.components import Informant, Wallet
from juno.math import floor_multiple
from juno.strategies import new_strategy
from juno.time import MAX_TIME_MS, time_ms
from juno.utils import unpack_symbol

from .agent import Agent
from .summary import Position, TradingSummary

_log = logging.getLogger(__name__)


class Live(Agent):

    def __init__(self, informant: Informant, wallet: Wallet, broker: Broker) -> None:
        super().__init__()
        self.informant = informant
        self.wallet = wallet
        self.broker = broker
        self.open_position: Optional[Position] = None

    async def run(self, exchange: str, symbol: str, interval: int, strategy_config: Dict[str, Any],
                  end: int = MAX_TIME_MS, restart_on_missed_candle: bool = True,
                  get_time: Optional[Callable[[], int]] = None) -> None:
        if not get_time:
            get_time = time_ms

        now = floor_multiple(get_time(), interval)
        assert end > now

        self.exchange = exchange
        self.symbol = symbol

        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        self.quote = self.wallet.get_balance(exchange, self.quote_asset).available

        fees = self.informant.get_fees(exchange, symbol)
        filters = self.informant.get_filters(exchange, symbol)

        assert self.quote > filters.price.min

        self.result = TradingSummary(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=now,
            quote=self.quote,
            fees=fees,
            filters=filters)
        self.open_position = None
        restart_count = 0

        while True:
            self.last_candle = None
            restart = False

            strategy = new_strategy(strategy_config)

            if restart_count == 0:
                # Adjust start to accommodate for the required history before a strategy becomes
                # effective. Only do it on first run because subsequent runs mean missed candles
                # and we don't want to fetch passed a missed candle.
                _log.info(f'fetching {strategy.req_history} candle(s) before start time to '
                          'warm-up strategy')
                start = now - strategy.req_history * interval

            async for candle in self.informant.stream_candles(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                    start=start,
                    end=end):
                if not candle.closed:
                    continue

                self.result.append_candle(candle)

                # Check if we have missed a candle.
                if self.last_candle and candle.time - self.last_candle.time >= interval * 2:
                    _log.warning(f'missed candle(s); last candle {self.last_candle}; current '
                                 f'candle {candle}')
                    if restart_on_missed_candle:
                        _log.info('restarting strategy')
                        start = candle.time
                        restart = True
                        restart_count += 1
                        break

                self.last_candle = candle
                advice = strategy.update(candle)

                if not self.open_position and advice == 1:
                    if not await self._try_open_position(candle):
                        _log.warning(f'quote balance too low to open a position; stopping')
                        break
                elif self.open_position and advice == -1:
                    await self._close_position(candle)

            if not restart:
                break

    async def finalize(self) -> None:
        if self.last_candle and self.open_position:
            _log.info('closing currently open position')
            await self._close_position(self.last_candle)
        _log.info(json.dumps(self.result, default=lambda o: o.__dict__, use_decimal=True))

    async def _try_open_position(self, candle: Candle) -> bool:
        res = await self.broker.buy(
            exchange=self.exchange,
            symbol=self.symbol,
            quote=self.quote,
            test=False)

        if res.status is OrderStatus.NOT_PLACED:
            return False

        self.open_position = Position(candle.time, res.fills)
        self.quote -= res.fills.total_quote

        await self.ee.emit('position_opened', self.open_position)

        return True

    async def _close_position(self, candle: Candle) -> None:
        assert self.open_position

        res = await self.broker.sell(
            exchange=self.exchange,
            symbol=self.symbol,
            base=self.open_position.total_size - self.open_position.fills.total_fee,
            test=False)

        position = self.open_position
        self.open_position = None
        position.close(candle.time, res.fills)
        self.result.append_position(position)
        self.quote += res.fills.total_quote - res.fills.total_fee

        await self.ee.emit('position_closed', position)
