from decimal import Decimal
from typing import Any, Callable, List, Optional, Type

from .solver import Solver
from juno import Advice, Candle, Fill, Fills, Position, TradingSummary
from juno.asyncio import list_async
from juno.components import Informant
from juno.strategies import Strategy
from juno.utils import unpack_symbol


class TradingContext:
    def __init__(self, quote: Decimal, summary: TradingSummary) -> None:
        self.quote = quote
        self.summary = summary
        self.open_position: Optional[Position] = None


class Python(Solver):
    def __init__(self, informant: Informant) -> None:
        self.informant = informant
        self.restart_on_missed_candle = False

    async def get(
        self, strategy_type: Type[Strategy], exchange: str, symbol: str, interval: int, start: int,
        end: int, quote: Decimal
    ) -> Callable[..., Any]:
        self.strategy_type = strategy_type
        self.candles = await list_async(
            self.informant.stream_candles(exchange, symbol, interval, start, end)
        )
        self.fees = self.informant.get_fees(exchange, symbol)
        self.filters = self.informant.get_filters(exchange, symbol)
        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        self.interval = interval
        self.start = start
        self.end = end
        self.quote = quote
        return self._solve

    def _solve(self, *args: Any) -> Any:
        ctx = TradingContext(self.quote, TradingSummary(
            interval=self.interval,
            start=self.start,
            quote=self.quote,
            fees=self.fees,
            filters=self.filters
        ))

        while True:
            self.last_candle = None
            restart = False

            strategy = self.strategy_type(*args)  # type: ignore

            for candle in self.candles:
                if not candle.closed:
                    continue

                ctx.summary.append_candle(candle)

                if self.last_candle and candle.time - self.last_candle.time >= self.interval * 2:
                    if self.restart_on_missed_candle:
                        restart = True
                        break

                self.last_candle = candle
                advice = strategy.update(candle)

                if not ctx.open_position and advice is Advice.BUY:
                    if not self._try_open_position(ctx, candle):
                        break
                elif ctx.open_position and advice is Advice.SELL:
                    self._close_position(ctx, candle)

            if not restart:
                break

        if self.last_candle and ctx.open_position:
            self._close_position(ctx, self.last_candle)

        return (
            float(ctx.summary.profit),
            float(ctx.summary.mean_drawdown),
            float(ctx.summary.max_drawdown),
            float(ctx.summary.mean_position_profit),
            ctx.summary.mean_position_duration,
        )

    def _try_open_position(self, ctx: TradingContext, candle: Candle) -> bool:
        price = candle.close

        size = self.filters.size.round_down(ctx.quote / price)
        if size == 0:
            return False

        fee = size * self.fees.taker

        ctx.open_position = Position(
            time=candle.time,
            fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.base_asset)])
        )

        ctx.quote -= size * price

        return True

    def _close_position(self, ctx: TradingContext, candle: Candle) -> None:
        assert ctx.open_position

        price = candle.close

        size = self.filters.size.round_down(
            ctx.open_position.total_size - ctx.open_position.fills.total_fee
        )

        quote = size * price
        fee = quote * self.fees.taker

        ctx.open_position.close(
            time=candle.time,
            fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.quote_asset)])
        )
        ctx.summary.append_position(ctx.open_position)
        ctx.open_position = None

        ctx.quote = quote - fee
