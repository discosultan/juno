from decimal import Decimal
from typing import Any, List, Type

from juno import Advice, Candle, Fees, Fill, Filters, InsufficientBalance, Interval
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.trading import (
    MissedCandlePolicy, Position, Statistics, TradingContext, TradingSummary,
    get_portfolio_statistics
)
from juno.utils import unpack_symbol

from .solver import Solver, SolverResult


class Python(Solver):
    def solve(
        self,
        base_fiat_candles: List[Candle],
        portfolio_candles: List[Candle],
        benchmark_stats: Statistics,
        strategy_type: Type[Strategy],
        quote: Decimal,
        candles: List[Candle],
        fees: Fees,
        filters: Filters,
        symbol: str,
        interval: Interval,
        missed_candle_policy: MissedCandlePolicy,
        trailing_stop: Decimal,
        *args: Any,
    ) -> SolverResult:
        summary = TradingSummary(
            interval=interval, start=candles[0].time, quote=quote, fees=fees, filters=filters
        )
        ctx = TradingContext(strategy_type(*args), quote)
        try:
            i = 0
            while True:
                restart = False

                for candle in candles[i:]:
                    i += 1
                    if not candle.closed:
                        continue

                    summary.append_candle(candle)

                    # TODO: python 3.8 assignment expression
                    if ctx.last_candle and candle.time - ctx.last_candle.time >= interval * 2:
                        if missed_candle_policy is MissedCandlePolicy.RESTART:
                            restart = True
                            ctx.strategy = strategy_type(*args)
                        elif missed_candle_policy is MissedCandlePolicy.LAST:
                            num_missed = (candle.time - ctx.last_candle.time) // interval - 1
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
                                _tick(ctx, summary, symbol, fees, filters, trailing_stop,
                                      missed_candle)

                    _tick(ctx, summary, symbol, fees, filters, trailing_stop, candle)

                    if restart:
                        break

                if not restart:
                    break

            if ctx.last_candle and ctx.open_position:
                _close_position(ctx, summary, symbol, fees, filters, ctx.last_candle)
        except InsufficientBalance:
            pass

        portfolio_stats = get_portfolio_statistics(
            benchmark_stats, base_fiat_candles, portfolio_candles, symbol, summary
        )

        return SolverResult.from_trading_summary(summary, portfolio_stats)


def _tick(
    ctx: TradingContext, summary: TradingSummary, symbol: str, fees: Fees,
    filters: Filters, trailing_stop: Decimal, candle: Candle
) -> None:
    ctx.strategy.update(candle)
    advice = ctx.strategy.advice

    if not ctx.open_position and advice is Advice.BUY:
        _try_open_position(ctx, symbol, fees, filters, candle)
        ctx.highest_close_since_position = candle.close
    elif ctx.open_position and advice is Advice.SELL:
        _close_position(ctx, summary, symbol, fees, filters, candle)
    elif trailing_stop != 0 and ctx.open_position:
        ctx.highest_close_since_position = max(ctx.highest_close_since_position, candle.close)
        trailing_factor = 1 - trailing_stop
        if candle.close <= ctx.highest_close_since_position * trailing_factor:
            _close_position(ctx, summary, symbol, fees, filters, candle)

    ctx.last_candle = candle


def _try_open_position(
    ctx: TradingContext, symbol: str, fees: Fees, filters: Filters, candle: Candle
) -> None:
    price = candle.close

    size = filters.size.round_down(ctx.quote / price)
    if size == 0:
        raise InsufficientBalance()

    fee = round_half_up(size * fees.taker, filters.base_precision)

    base_asset, _ = unpack_symbol(symbol)
    ctx.open_position = Position(
        time=candle.time,
        fills=[Fill(price=price, size=size, fee=fee, fee_asset=base_asset)]
    )

    ctx.quote -= size * price


def _close_position(
    ctx: TradingContext, summary: TradingSummary, symbol: str, fees: Fees, filters: Filters,
    candle: Candle
) -> None:
    pos = ctx.open_position
    assert pos

    price = candle.close

    size = filters.size.round_down(pos.base_gain)

    quote = size * price
    fee = round_half_up(quote * fees.taker, filters.quote_precision)

    _, quote_asset = unpack_symbol(symbol)
    pos.close(
        time=candle.time,
        fills=[Fill(price=price, size=size, fee=fee, fee_asset=quote_asset)]
    )
    summary.append_position(pos)

    ctx.quote += quote - fee

    ctx.open_position = None
