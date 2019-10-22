from decimal import Decimal
from typing import Any, Callable, Optional, Type

from juno import (
    Advice, Candle, Fees, Fill, Fills, Filters, Position, TradingContext, TradingSummary
)
from juno.asyncio import list_async
from juno.components import Chandler, Informant
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.utils import unpack_symbol

from .solver import Solver, SolverResult


class Python(Solver):
    def __init__(self, chandler: Chandler, informant: Informant) -> None:
        self.chandler = chandler
        self.informant = informant

    async def get(
        self,
        strategy_type: Type[Strategy],
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        end: int,
        quote: Decimal,
    ) -> Callable[..., Any]:
        candles = await list_async(
            self.chandler.stream_candles(exchange, symbol, interval, start, end)
        )
        fees, filters = self.informant.get_fees_filters(exchange, symbol)
        base_asset, quote_asset = unpack_symbol(symbol)

        def backtest(
            restart_on_missed_candle: bool,
            trailing_stop: Decimal,
            *args: Any,
        ) -> SolverResult:
            ctx = TradingContext(quote)
            summary = TradingSummary(
                interval=interval, start=start, quote=quote, fees=fees, filters=filters
            )
            while True:
                restart = False
                last_candle = None
                strategy = strategy_type(*args)  # type: ignore

                for candle in candles:
                    if not candle.closed:
                        continue

                    summary.append_candle(candle)

                    if last_candle and candle.time - last_candle.time >= interval * 2:
                        if restart_on_missed_candle:
                            restart = True
                            break

                    last_candle = candle
                    advice = strategy.update(candle)

                    if not ctx.open_position and advice is Advice.BUY:
                        if not _try_open_position(ctx, base_asset, fees, filters, candle):
                            break
                        highest_close_since_position = candle.close
                    elif ctx.open_position and advice is Advice.SELL:
                        _close_position(ctx, summary, quote_asset, fees, filters, candle)
                    elif trailing_stop is not None and ctx.open_position:
                        highest_close_since_position = max(highest_close_since_position,
                                                           candle.close)
                        trailing_factor = Decimal(1) - trailing_stop
                        if candle.close <= highest_close_since_position * trailing_factor:
                            _close_position(ctx, summary, quote_asset, fees, filters, candle)

                if not restart:
                    break

            if last_candle and ctx.open_position:
                _close_position(ctx, summary, quote_asset, fees, filters, last_candle)

            return SolverResult(
                float(summary.profit),
                float(summary.mean_drawdown),
                float(summary.max_drawdown),
                float(summary.mean_position_profit),
                summary.mean_position_duration,
            )

        return backtest


def _try_open_position(
    ctx: TradingContext, base_asset: str, fees: Fees, filters: Filters, candle: Candle
) -> Optional[Position]:
    price = candle.close

    size = filters.size.round_down(ctx.quote / price)
    if size == 0:
        return None

    fee = round_half_up(size * fees.taker, filters.base_precision)

    ctx.open_position = Position(
        time=candle.time,
        fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=base_asset)])
    )

    ctx.quote -= size * price

    return ctx.open_position


def _close_position(
    ctx: TradingContext, summary: TradingSummary, quote_asset: str, fees: Fees, filters: Filters,
    candle: Candle
) -> Position:
    pos = ctx.open_position
    assert pos

    price = candle.close

    size = filters.size.round_down(pos.fills.total_size - pos.fills.total_fee)

    quote = size * price
    fee = round_half_up(quote * fees.taker, filters.quote_precision)

    pos.close(
        time=candle.time,
        fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=quote_asset)])
    )
    summary.append_position(pos)

    ctx.quote += quote - fee

    ctx.open_position = None
    return pos
