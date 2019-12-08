import logging
from decimal import Decimal
from typing import Callable, Optional

from juno import Advice, Candle, Fill, Fills, InsufficientBalance
from juno.brokers import Broker
from juno.components import Chandler, Informant
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.utils import EventEmitter, format_attrs_as_json, unpack_symbol

from .common import Position, TradingContext, TradingSummary


class Trader:
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
        test: bool = True,  # No effect if broker is None.
        event: EventEmitter = EventEmitter(),
        log: logging.Logger = logging.getLogger(__name__),
        missed_candle_policy: str = 'ignore',
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),  # 0 means disabled.
    ) -> None:
        assert start >= 0
        assert end > 0
        assert end > start
        assert 0 <= trailing_stop < 1
        assert missed_candle_policy in ['ignore', 'restart', 'last']

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
        self.missed_candle_policy = missed_candle_policy
        self.adjust_start = adjust_start
        self.trailing_stop = trailing_stop

        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        fees, filters = informant.get_fees_filters(exchange, symbol)
        self.summary = TradingSummary(
            interval=interval, start=start, quote=quote, fees=fees, filters=filters
        )
        self.ctx = TradingContext(new_strategy(), quote)

    async def run(self) -> None:
        ctx = self.ctx
        start = self.start
        restart_count = 0
        try:
            while True:
                restart = False

                if self.adjust_start and restart_count == 0:
                    # Adjust start to accommodate for the required history before a strategy
                    # becomes effective. Only do it on first run because subsequent runs mean
                    # missed candles and we don't want to fetch passed a missed candle.
                    self.log.info(
                        f'fetching {ctx.strategy.req_history} candle(s) before start time to '
                        'warm-up strategy'
                    )
                    start -= ctx.strategy.req_history * self.interval

                async for candle in self.chandler.stream_candles(
                    exchange=self.exchange,
                    symbol=self.symbol,
                    interval=self.interval,
                    start=start,
                    end=self.end
                ):
                    # Check if we have missed a candle.
                    if ctx.last_candle and candle.time - ctx.last_candle.time >= self.interval * 2:
                        # TODO: python 3.8 assignment expression
                        num_missed = (candle.time - ctx.last_candle.time) // self.interval - 1
                        self.log.warning(
                            f'missed {num_missed} candle(s); last candle {ctx.last_candle}; '
                            f'current candle {candle}'
                        )
                        if self.missed_candle_policy == 'restart':
                            self.log.info('restarting strategy')
                            restart = True
                            ctx.strategy = self.new_strategy()
                            start = candle.time + self.interval
                            restart_count += 1
                        elif self.missed_candle_policy == 'last':
                            self.log.info('replaying missed candles with last candle values')
                            for i in range(1, num_missed + 1):
                                missed_candle = Candle(
                                    time=ctx.last_candle.time + i * self.interval,
                                    open=ctx.last_candle.open,
                                    high=ctx.last_candle.high,
                                    low=ctx.last_candle.low,
                                    close=ctx.last_candle.close,
                                    volume=ctx.last_candle.volume,
                                    closed=ctx.last_candle.closed
                                )
                                await self._tick(missed_candle)

                    await self._tick(candle)

                    if restart:
                        break

                if not restart:
                    break
        finally:
            if ctx.last_candle and ctx.open_position:
                self.log.info('ending trading but position open; closing')
                await self._close_position(candle=ctx.last_candle)
            print([p.duration for p in self.summary.positions])

    async def _tick(self, candle: Candle) -> None:
        ctx = self.ctx
        self.summary.append_candle(candle)

        advice = ctx.strategy.update(candle)

        if not ctx.open_position and advice is Advice.BUY:
            await self._open_position(candle=candle)
            ctx.highest_close_since_position = candle.close
        elif ctx.open_position and advice is Advice.SELL:
            await self._close_position(candle=candle)
        elif self.trailing_stop != 0 and ctx.open_position:
            ctx.highest_close_since_position = max(
                ctx.highest_close_since_position, candle.close
            )
            trailing_factor = 1 - self.trailing_stop
            if candle.close <= ctx.highest_close_since_position * trailing_factor:
                self.log.info(f'trailing stop hit at {self.trailing_stop}; selling')
                await self._close_position(candle=candle)

        ctx.last_candle = candle

    async def _open_position(self, candle: Candle) -> None:
        ctx = self.ctx
        if self.broker:
            res = await self.broker.buy(
                exchange=self.exchange, symbol=self.symbol, quote=ctx.quote, test=self.test
            )

            ctx.open_position = Position(candle.time, res.fills)
            ctx.quote -= res.fills.total_quote
        else:
            price = candle.close
            fees, filters = self.informant.get_fees_filters(self.exchange, self.symbol)

            size = filters.size.round_down(ctx.quote / price)
            if size == 0:
                raise InsufficientBalance()

            fee = round_half_up(size * fees.taker, filters.base_precision)

            ctx.open_position = Position(
                time=candle.time,
                fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.base_asset)])
            )

            ctx.quote -= size * price

        self.log.info(f'position opened at candle: {candle}')
        self.log.debug(format_attrs_as_json(ctx.open_position))
        await self.event.emit('position_opened', ctx.open_position)

    async def _close_position(self, candle: Candle) -> None:
        ctx = self.ctx
        pos = ctx.open_position
        assert pos

        if self.broker:
            res = await self.broker.sell(
                exchange=self.exchange,
                symbol=self.symbol,
                base=pos.fills.total_size - pos.fills.total_fee,
                test=self.test
            )

            pos.close(candle.time, res.fills)
            ctx.quote += res.fills.total_quote - res.fills.total_fee
        else:
            price = candle.close
            fees, filters = self.informant.get_fees_filters(self.exchange, self.symbol)
            size = filters.size.round_down(pos.fills.total_size - pos.fills.total_fee)

            quote = size * price
            fee = round_half_up(quote * fees.taker, filters.quote_precision)

            pos.close(
                time=candle.time,
                fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.quote_asset)])
            )

            ctx.quote += quote - fee

        ctx.open_position = None
        self.summary.append_position(pos)
        self.log.info(f'position closed at candle: {candle}')
        self.log.debug(format_attrs_as_json(pos))
        await self.event.emit('position_closed', pos)
