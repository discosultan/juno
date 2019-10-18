import logging
from decimal import Decimal
from typing import Callable, Optional

from juno import (
    Advice, Candle, Fill, Fills, InsufficientBalance
)
from juno.brokers import Broker
from juno.components import Chandler, Informant
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.utils import EventEmitter, unpack_symbol

from .common import Position, TradingContext, TradingSummary


class TradingLoop:
    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        end: int,
        quote: Decimal,
        new_strategy: Callable[[], Strategy],
        broker: Optional[Broker] = None,
        test: bool = True,  # No effect if broker is None
        event: EventEmitter = EventEmitter(),
        log: logging.Logger = logging.getLogger(__name__),
        restart_on_missed_candle: bool = False,
        adjust_start: bool = True,
        trailing_stop: Optional[Decimal] = None,
    ) -> None:
        assert start >= 0
        assert end > 0
        assert end > start
        assert not trailing_stop or Decimal(1) > trailing_stop or trailing_stop > Decimal(0)

        self.chandler = chandler
        self.informant = informant
        self.exchange = exchange
        self.symbol = symbol
        self.interval = interval
        self.start = start
        self.end = end
        self.quote = quote
        self.new_strategy = new_strategy
        self.broker = broker
        self.test = test
        self.event = event
        self.log = log
        self.restart_on_missed_candle = restart_on_missed_candle
        self.adjust_start = adjust_start
        self.trailing_stop = trailing_stop

        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        fees, filters = informant.get_fees_filters(exchange, symbol)
        self.summary = TradingSummary(
            interval=interval, start=start, quote=quote, fees=fees, filters=filters
        )
        self.ctx = TradingContext(quote)

    async def run(self) -> None:
        start = self.start
        restart_count = 0
        try:
            while True:
                restart = False
                last_candle = None
                strategy = self.new_strategy()

                if self.adjust_start and restart_count == 0:
                    # Adjust start to accommodate for the required history before a strategy
                    # becomes effective. Only do it on first run because subsequent runs mean
                    # missed candles and we don't want to fetch passed a missed candle.
                    self.log.info(
                        f'fetching {strategy.req_history} candle(s) before start time to warm-up '
                        'strategy'
                    )
                    start -= strategy.req_history * self.interval

                async for candle in self.chandler.stream_candles(
                    exchange=self.exchange, symbol=self.symbol, interval=self.interval,
                    start=start, end=self.end
                ):
                    self.summary.append_candle(candle)

                    # Check if we have missed a candle.
                    if last_candle and candle.time - last_candle.time >= self.interval * 2:
                        self.log.warning(
                            f'missed candle(s); last candle {last_candle}; current candle {candle}'
                        )
                        if self.restart_on_missed_candle:
                            self.log.info('restarting strategy')
                            start = candle.time
                            strategy = self.new_strategy()
                            restart = True
                            restart_count += 1
                            break

                    last_candle = candle
                    advice = strategy.update(candle)

                    if not self.ctx.open_position and advice is Advice.BUY:
                        await self._open_position(candle=candle)
                        self.highest_close_since_position = candle.close
                    elif self.ctx.open_position and advice is Advice.SELL:
                        await self._close_position(candle=candle)
                    elif self.trailing_stop is not None and self.ctx.open_position:
                        self.highest_close_since_position = max(self.highest_close_since_position,
                                                                candle.close)
                        trailing_factor = Decimal(1) - self.trailing_stop
                        if candle.close <= self.highest_close_since_position * trailing_factor:
                            self.log.info(f'trailing stop hit at {self.trailing_stop}; selling')
                            await self._close_position(candle=candle)

                if not restart:
                    break
        finally:
            if last_candle and self.ctx.open_position:
                self.log.info('closing currently open position')
                await self._close_position(candle=candle)

    async def _open_position(self, candle: Candle) -> None:
        if self.broker:
            res = await self.broker.buy(
                exchange=self.exchange, symbol=self.symbol, quote=self.ctx.quote, test=self.test
            )

            self.ctx.open_position = Position(candle.time, res.fills)
            self.ctx.quote -= res.fills.total_quote
        else:
            price = candle.close
            fees, filters = self.informant.get_fees_filters(self.exchange, self.symbol)

            size = filters.size.round_down(self.ctx.quote / price)
            if size == 0:
                raise InsufficientBalance()

            fee = round_half_up(size * fees.taker, filters.base_precision)

            self.ctx.open_position = Position(
                time=candle.time,
                fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.base_asset)])
            )

            self.ctx.quote -= size * price

        await self.event.emit('position_opened', self.ctx.open_position)

    async def _close_position(self, candle: Candle) -> None:
        pos = self.ctx.open_position
        assert pos

        if self.broker:
            res = await self.broker.sell(
                exchange=self.exchange,
                symbol=self.symbol,
                base=pos.fills.total_size - pos.fills.total_fee,
                test=self.test
            )

            pos.close(candle.time, res.fills)
            self.ctx.quote += res.fills.total_quote - res.fills.total_fee
        else:
            price = candle.close
            fees, filters = self.informant.get_fees_filters(self.exchange, self.symbol)
            size = filters.size.round_down(pos.total_size - pos.fills.total_fee)

            quote = size * price
            fee = round_half_up(quote * fees.taker, filters.quote_precision)

            pos.close(
                time=candle.time,
                fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.quote_asset)])
            )

            self.ctx.quote += quote - fee

        self.summary.append_position(pos)
        self.ctx.open_position = None
        await self.event.emit('position_closed', pos)
