from decimal import Decimal
from typing import Any, Callable, Type

from .solver import Solver, SolverResult
from juno import Advice
from juno.asyncio import list_async
from juno.components import Informant
from juno.strategies import Strategy
from juno.trading import TradingContext, try_open_position, close_position


class Python(Solver):
    def __init__(self, informant: Informant) -> None:
        self.informant = informant

    async def get(
        self, strategy_type: Type[Strategy], exchange: str, symbol: str, interval: int, start: int,
        end: int, quote: Decimal
    ) -> Callable[..., Any]:
        restart_on_missed_candle = False
        candles = await list_async(
            self.informant.stream_candles(exchange, symbol, interval, start, end)
        )
        fees = self.informant.get_fees(exchange, symbol)
        filters = self.informant.get_filters(exchange, symbol)

        def backtest(self, *args: Any) -> SolverResult:
            ctx = TradingContext(symbol, interval, start, quote, fees)

            while True:
                last_candle = None
                restart = False

                strategy = strategy_type(*args)  # type: ignore

                for candle in candles:
                    if not candle.closed:
                        continue

                    ctx.summary.append_candle(candle)

                    if last_candle and candle.time - last_candle.time >= interval * 2:
                        if restart_on_missed_candle:
                            restart = True
                            break

                    last_candle = candle
                    advice = strategy.update(candle)

                    if not ctx.open_position and advice is Advice.BUY:
                        if not try_open_position(ctx, fees, filters, candle):
                            break
                    elif ctx.open_position and advice is Advice.SELL:
                        close_position(ctx, fees, filters, candle)

                if not restart:
                    break

            if last_candle and ctx.open_position:
                close_position(ctx, fees, filters, last_candle)

            return SolverResult(
                float(ctx.summary.profit),
                float(ctx.summary.mean_drawdown),
                float(ctx.summary.max_drawdown),
                float(ctx.summary.mean_position_profit),
                ctx.summary.mean_position_duration,
            )

        return backtest
