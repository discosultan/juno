import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from juno import Advice, Candle, Fill, InsufficientBalance, Interval, Timestamp
from juno.brokers import Broker
from juno.components import Chandler, Event, Informant
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.utils import tonamedtuple, unpack_symbol

from .common import MissedCandlePolicy, Position, TradingSummary

_log = logging.getLogger(__name__)


class _Context:
    def __init__(
        self,
        strategy: Strategy,
        quote: Decimal,
        exchange: str,
        symbol: str,
        trailing_stop: Decimal,
        test: bool,
        channel: str,
        summary: TradingSummary,
    ) -> None:
        # Mutable.
        self.strategy = strategy
        self.quote = quote
        self.open_position: Optional[Position] = None
        self.first_candle: Optional[Candle] = None
        self.last_candle: Optional[Candle] = None
        self.highest_close_since_position = Decimal('0.0')
        self.summary = summary

        # Immutable.
        self.exchange = exchange
        self.symbol = symbol
        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        self.trailing_stop = trailing_stop
        self.test = test
        self.channel = channel


class Trader:
    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        broker: Optional[Broker] = None,
        event: Event = Event(),
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._broker = broker
        self._event = event

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        start: Timestamp,
        end: Timestamp,
        quote: Decimal,
        strategy_type: Type[Strategy],
        strategy_args: Union[List[Any], Tuple[Any]] = [],
        strategy_kwargs: Dict[str, Any] = {},
        test: bool = True,  # No effect if broker is None.
        channel: str = 'default',
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),  # 0 means disabled.
        summary: Optional[TradingSummary] = None,
    ) -> TradingSummary:
        assert start >= 0
        assert end > 0
        assert end > start
        assert 0 <= trailing_stop < 1

        summary = summary or TradingSummary(start=start, quote=quote)
        ctx = _Context(
            strategy=strategy_type(*strategy_args, **strategy_kwargs),
            quote=quote,
            exchange=exchange,
            symbol=symbol,
            trailing_stop=trailing_stop,
            test=test,
            channel=channel,
            summary=summary
        )

        adjusted_start = start
        if adjust_start:
            # Adjust start to accommodate for the required history before a strategy
            # becomes effective. Only do it on first run because subsequent runs mean
            # missed candles and we don't want to fetch passed a missed candle.
            _log.info(
                f'fetching {ctx.strategy.req_history} candle(s) before start time to '
                'warm-up strategy'
            )
            adjusted_start -= ctx.strategy.req_history * interval

        try:
            while True:
                restart = False

                async for candle in self._chandler.stream_candles(
                    exchange=exchange, symbol=symbol, interval=interval, start=adjusted_start,
                    end=end
                ):
                    # Check if we have missed a candle.
                    if ctx.last_candle and candle.time - ctx.last_candle.time >= interval * 2:
                        # TODO: walrus operator
                        num_missed = (candle.time - ctx.last_candle.time) // interval - 1
                        if missed_candle_policy is MissedCandlePolicy.RESTART:
                            _log.info('restarting strategy due to missed candle(s)')
                            restart = True
                            ctx.strategy = strategy_type(*strategy_args, **strategy_kwargs)
                            adjusted_start = candle.time + interval
                        elif missed_candle_policy is MissedCandlePolicy.LAST:
                            _log.info(f'filling {num_missed} missed candles with last values')
                            last_candle = ctx.last_candle
                            for i in range(1, num_missed + 1):
                                missed_candle = Candle(
                                    time=last_candle.time + i * interval,
                                    open=last_candle.open,
                                    high=last_candle.high,
                                    low=last_candle.low,
                                    close=last_candle.close,
                                    volume=last_candle.volume,
                                    closed=last_candle.closed
                                )
                                await self._tick(ctx, missed_candle)

                    await self._tick(ctx, candle)

                    if restart:
                        break

                if not restart:
                    break
        finally:
            if ctx.last_candle and ctx.open_position:
                _log.info('ending trading but position open; closing')
                await self._close_position(ctx, ctx.last_candle)
            if ctx.last_candle:
                ctx.summary.finish(ctx.last_candle.time + interval)
            else:
                ctx.summary.finish(start)

        return ctx.summary

    async def _tick(self, ctx: _Context, candle: Candle) -> None:
        ctx.strategy.update(candle)
        advice = ctx.strategy.advice

        if not ctx.open_position and advice is Advice.BUY:
            await self._open_position(ctx, candle)
            ctx.highest_close_since_position = candle.close
        elif ctx.open_position and advice is Advice.SELL:
            await self._close_position(ctx, candle)
        elif ctx.trailing_stop != 0 and ctx.open_position:
            ctx.highest_close_since_position = max(
                ctx.highest_close_since_position, candle.close
            )
            trailing_factor = 1 - ctx.trailing_stop
            if candle.close <= ctx.highest_close_since_position * trailing_factor:
                _log.info(f'trailing stop hit at {ctx.trailing_stop}; selling')
                await self._close_position(ctx, candle)

        if not ctx.last_candle:
            _log.info(f'first candle {candle}')
            ctx.first_candle = candle
        ctx.last_candle = candle

    async def _open_position(self, ctx: _Context, candle: Candle) -> None:
        if self._broker:
            res = await self._broker.buy(
                exchange=ctx.exchange,
                symbol=ctx.symbol,
                quote=ctx.quote,
                test=ctx.test
            )

            ctx.open_position = Position(symbol=ctx.symbol, time=candle.time, fills=res.fills)

            ctx.quote -= Fill.total_quote(res.fills)
        else:
            price = candle.close
            fees, filters = self._informant.get_fees_filters(ctx.exchange, ctx.symbol)

            size = filters.size.round_down(ctx.quote / price)
            if size == 0:
                raise InsufficientBalance()

            fee = round_half_up(size * fees.taker, filters.base_precision)

            ctx.open_position = Position(
                symbol=ctx.symbol,
                time=candle.time,
                fills=[Fill(price=price, size=size, fee=fee, fee_asset=ctx.base_asset)]
            )

            ctx.quote -= size * price

        _log.info(f'position opened: {candle}')
        _log.debug(tonamedtuple(ctx.open_position))
        await self._event.emit(ctx.channel, 'position_opened', ctx.open_position)

    async def _close_position(self, ctx: _Context, candle: Candle) -> None:
        pos = ctx.open_position
        assert pos

        if self._broker:
            res = await self._broker.sell(
                exchange=ctx.exchange,
                symbol=ctx.symbol,
                base=pos.base_gain,
                test=ctx.test
            )

            pos.close(
                time=candle.time,
                fills=res.fills
            )

            ctx.quote += Fill.total_quote(res.fills) - Fill.total_fee(res.fills)
        else:
            price = candle.close
            fees, filters = self._informant.get_fees_filters(ctx.exchange, ctx.symbol)
            size = filters.size.round_down(pos.base_gain)

            quote = size * price
            fee = round_half_up(quote * fees.taker, filters.quote_precision)

            pos.close(
                time=candle.time,
                fills=[Fill(price=price, size=size, fee=fee, fee_asset=ctx.quote_asset)]
            )

            ctx.quote += quote - fee

        ctx.open_position = None
        ctx.summary.append_position(pos)
        _log.info(f'position closed: {candle}')
        _log.debug(tonamedtuple(pos))
        await self._event.emit(ctx.channel, 'position_closed', pos)
