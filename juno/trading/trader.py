import logging
from decimal import Decimal
from typing import Callable, Optional

from juno import Advice, Candle, Fill, InsufficientBalance, Interval, Timestamp
from juno.brokers import Broker
from juno.components import Chandler, Informant
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.utils import EventEmitter, format_attrs_as_json, unpack_symbol

from .common import MissedCandlePolicy, Position, TradingContext, TradingSummary

_log = logging.getLogger(__name__)


class Trader:
    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        exchange: str,
        symbol: str,
        interval: Interval,
        start: Timestamp,
        end: Timestamp,
        quote: Decimal,
        new_strategy: Callable[[], Strategy],
        broker: Optional[Broker] = None,
        test: bool = True,  # No effect if broker is None.
        event: EventEmitter = EventEmitter(),
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),  # 0 means disabled.
        summary: Optional[TradingSummary] = None,
    ) -> None:
        assert start >= 0
        assert end > 0
        assert end > start
        assert 0 <= trailing_stop < 1

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
        self.missed_candle_policy = missed_candle_policy
        self.adjust_start = adjust_start
        self.trailing_stop = trailing_stop

        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        fees, filters = informant.get_fees_filters(exchange, symbol)
        self.summary = summary or TradingSummary(start=start, quote=quote)
        self.owns_summary = summary is None
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
                    _log.info(
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
                        # TODO: walrus operator
                        num_missed = (candle.time - ctx.last_candle.time) // self.interval - 1
                        if self.missed_candle_policy is MissedCandlePolicy.RESTART:
                            _log.info('restarting strategy due to missed candle(s)')
                            restart = True
                            ctx.strategy = self.new_strategy()
                            start = candle.time + self.interval
                            restart_count += 1
                        elif self.missed_candle_policy is MissedCandlePolicy.LAST:
                            _log.info(f'filling {num_missed} missed candles with last values')
                            last_candle = ctx.last_candle
                            for i in range(1, num_missed + 1):
                                missed_candle = Candle(
                                    time=last_candle.time + i * self.interval,
                                    open=last_candle.open,
                                    high=last_candle.high,
                                    low=last_candle.low,
                                    close=last_candle.close,
                                    volume=last_candle.volume,
                                    closed=last_candle.closed
                                )
                                await self._tick(missed_candle)

                    await self._tick(candle)

                    if restart:
                        break

                if not restart:
                    break
        finally:
            if ctx.last_candle and ctx.open_position:
                _log.info('ending trading but position open; closing')
                await self._close_position(candle=ctx.last_candle)
            if self.owns_summary and ctx.last_candle:
                self.summary.finish(ctx.last_candle.time + self.interval)

    async def _tick(self, candle: Candle) -> None:
        ctx = self.ctx

        ctx.strategy.update(candle)
        advice = ctx.strategy.advice

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
                _log.info(f'trailing stop hit at {self.trailing_stop}; selling')
                await self._close_position(candle=candle)

        if not ctx.last_candle:
            _log.info(f'first candle {candle}')
            ctx.first_candle = candle
        ctx.last_candle = candle

    async def _open_position(self, candle: Candle) -> None:
        ctx = self.ctx
        if self.broker:
            res = await self.broker.buy(
                exchange=self.exchange, symbol=self.symbol, quote=ctx.quote, test=self.test
            )

            ctx.open_position = Position(candle.time, res.fills)
            ctx.quote -= Fill.total_quote(res.fills)
        else:
            price = candle.close
            fees, filters = self.informant.get_fees_filters(self.exchange, self.symbol)

            size = filters.size.round_down(ctx.quote / price)
            if size == 0:
                raise InsufficientBalance()

            fee = round_half_up(size * fees.taker, filters.base_precision)

            ctx.open_position = Position(
                time=candle.time,
                fills=[Fill(price=price, size=size, fee=fee, fee_asset=self.base_asset)]
            )

            ctx.quote -= size * price

        _log.info(f'position opened: {candle}')
        _log.debug(format_attrs_as_json(ctx.open_position))
        await self.event.emit('position_opened', ctx.open_position)

    async def _close_position(self, candle: Candle) -> None:
        ctx = self.ctx
        pos = ctx.open_position
        assert pos

        if self.broker:
            res = await self.broker.sell(
                exchange=self.exchange,
                symbol=self.symbol,
                base=pos.base_gain,
                test=self.test
            )

            pos.close(candle.time, res.fills)
            ctx.quote += Fill.total_quote(res.fills) - Fill.total_fee(res.fills)
        else:
            price = candle.close
            fees, filters = self.informant.get_fees_filters(self.exchange, self.symbol)
            size = filters.size.round_down(pos.base_gain)

            quote = size * price
            fee = round_half_up(quote * fees.taker, filters.quote_precision)

            pos.close(
                time=candle.time,
                fills=[Fill(price=price, size=size, fee=fee, fee_asset=self.quote_asset)]
            )

            ctx.quote += quote - fee

        ctx.open_position = None
        self.summary.append_position(pos)
        _log.info(f'position closed: {candle}')
        _log.debug(format_attrs_as_json(pos))
        await self.event.emit('position_closed', pos)
