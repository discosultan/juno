import logging
from typing import Any, Callable, Dict, Optional

from juno import Candle, Side
from juno.components import Informant, Orderbook, Wallet
from juno.math import floor_multiple
from juno.strategies import new_strategy
from juno.time import MAX_TIME_MS, time_ms
from juno.utils import unpack_symbol

from .agent import Agent
from .summary import Position, TradingSummary

_log = logging.getLogger(__name__)


class Live(Agent):

    required_components = ['informant', 'orderbook', 'wallet']
    open_position: Optional[Position]

    async def run(self, exchange: str, symbol: str, interval: int, strategy_config: Dict[str, Any],
                  end: int = MAX_TIME_MS, restart_on_missed_candle: bool = True,
                  get_time: Optional[Callable[[], int]] = None) -> TradingSummary:
        if not get_time:
            get_time = time_ms

        now = floor_multiple(get_time(), interval)
        assert end > now

        self.exchange = exchange
        self.symbol = symbol

        informant: Informant = self.components['informant']
        self.orderbook: Orderbook = self.components['orderbook']
        self.wallet: Wallet = self.components['wallet']

        self.fees = informant.get_fees(exchange)
        _log.info(f'Fees: {self.fees}')

        self.symbol_info = informant.get_symbol_info(exchange, symbol)
        _log.info(f'Symbol info: {self.symbol_info}')

        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        self.quote = self.wallet.get_balance(exchange, self.quote_asset).available
        _log.info(f'Available balance: {self.quote} {self.quote_asset}')

        self.summary = TradingSummary(exchange, symbol, interval, now, end, self.quote, self.fees,
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
                    if not await self._try_open_position(candle):
                        _log.warning(f'quote balance too low to open a position; stopping')
                        break
                elif self.open_position and advice == -1:
                    await self._close_position(candle)

            if not restart:
                break

        if last_candle is not None and self.open_position:
            await self._close_position(last_candle)

        return self.summary

    async def _try_open_position(self, candle: Candle) -> bool:
        asks = self.orderbook.find_market_order_asks(self.exchange, self.symbol, self.quote,
                                                     self.symbol_info, self.fees)
        if asks.total_size == 0:
            return False

        res = await self.orderbook.place_order(
            exchange=self.exchange,
            symbol=self.symbol,
            side=Side.BUY,
            size=asks.total_size,
            test=False)

        self.open_position = Position(candle.time, res.fills)
        self.quote -= res.fills.total_quote

        await self.ee.emit('position_opened', self.open_position)

        return True

    async def _close_position(self, candle: Candle) -> None:
        assert self.open_position

        base = self.open_position.total_size - self.open_position.fills.total_fee
        bids = self.orderbook.find_market_order_bids(self.exchange, self.symbol, base,
                                                     self.symbol_info, self.fees)

        res = await self.orderbook.place_order(
            exchange=self.exchange,
            symbol=self.symbol,
            side=Side.SELL,
            size=bids.total_size,
            test=False)

        position = self.open_position
        self.open_position = None
        position.close(candle.time, res.fills)
        self.summary.append_position(position)
        self.quote += bids.total_quote - res.fills.total_fee

        await self.ee.emit('position_closed', position)
        await self.ee.emit('summary', self.summary)
