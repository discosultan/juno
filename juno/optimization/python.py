from decimal import Decimal
from typing import Any, Dict, List, Optional, Type

import pandas as pd

from juno import Advice, Candle, Fees, Fill, Filters, InsufficientBalance, Interval, Timestamp
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.trading import MissedCandlePolicy, OpenLongPosition, TradingSummary, analyse_portfolio
from juno.utils import unpack_symbol

from .solver import Solver, SolverResult


# TODO: Refactor to state object.
class _Context:
    def __init__(self, strategy: Strategy, quote: Decimal) -> None:
        self.strategy = strategy
        self.quote = quote
        self.open_position: Optional[OpenLongPosition] = None
        self.first_candle: Optional[Candle] = None
        self.last_candle: Optional[Candle] = None
        self.highest_close_since_position = Decimal('0.0')


# We could rename the class to PythonSolver but it's more user-friendly to allow people to just
# specify { "solver": "python" } in config.
class Python(Solver):
    def solve(
        self,
        fiat_daily_prices: Dict[str, List[Decimal]],
        benchmark_g_returns: pd.Series,
        strategy_type: Type[Strategy],
        start: Timestamp,
        end: Timestamp,
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
        summary = _trade(
            strategy_type,
            quote,
            candles,
            fees,
            filters,
            symbol,
            interval,
            missed_candle_policy,
            trailing_stop,
            *args,
        )

        portfolio = analyse_portfolio(benchmark_g_returns, fiat_daily_prices, summary)

        return SolverResult.from_trading_summary(summary, portfolio.stats)


def _trade(
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
):
    summary = TradingSummary(start=candles[0].time, quote=quote)
    ctx = _Context(strategy_type(*args), quote)
    try:
        i = 0
        while True:
            restart = False

            for candle in candles[i:]:
                i += 1
                if not candle.closed:
                    continue

                # TODO: python 3.8 assignment expression
                if (
                    missed_candle_policy is not MissedCandlePolicy.IGNORE
                    and ctx.last_candle
                    and candle.time - ctx.last_candle.time >= interval * 2
                ):
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
                    else:
                        raise NotImplementedError()

                _tick(ctx, summary, symbol, fees, filters, trailing_stop, candle)

                if restart:
                    break

            if not restart:
                break

        if ctx.last_candle and ctx.open_position:
            _close_position(ctx, summary, symbol, fees, filters, ctx.last_candle)
    except InsufficientBalance:
        pass

    summary.finish(candles[-1].time + interval)
    return summary


def _tick(
    ctx: _Context, summary: TradingSummary, symbol: str, fees: Fees, filters: Filters,
    trailing_stop: Decimal, candle: Candle
) -> None:
    advice = ctx.strategy.update(candle)

    if not ctx.open_position and advice is Advice.LONG:
        _try_open_position(ctx, symbol, fees, filters, candle)
        ctx.highest_close_since_position = candle.close
    elif ctx.open_position and advice is Advice.SHORT:
        _close_position(ctx, summary, symbol, fees, filters, candle)
    elif trailing_stop != 0 and ctx.open_position:
        ctx.highest_close_since_position = max(ctx.highest_close_since_position, candle.close)
        trailing_factor = 1 - trailing_stop
        if candle.close <= ctx.highest_close_since_position * trailing_factor:
            _close_position(ctx, summary, symbol, fees, filters, candle)

    if not ctx.first_candle:
        ctx.first_candle = candle
    ctx.last_candle = candle


def _try_open_position(
    ctx: _Context, symbol: str, fees: Fees, filters: Filters, candle: Candle
) -> None:
    price = candle.close

    size = filters.size.round_down(ctx.quote / price)
    if size == 0:
        raise InsufficientBalance()

    quote = round_half_up(size * price, filters.quote_precision)
    fee = round_half_up(size * fees.taker, filters.base_precision)

    base_asset, _ = unpack_symbol(symbol)
    ctx.open_position = OpenLongPosition(
        symbol=symbol,
        time=candle.time,
        fills=[Fill(
            price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
        )],
    )

    ctx.quote -= quote


def _close_position(
    ctx: _Context, summary: TradingSummary, symbol: str, fees: Fees, filters: Filters,
    candle: Candle
) -> None:
    assert ctx.open_position

    price = candle.close

    size = filters.size.round_down(ctx.open_position.base_gain)

    quote = round_half_up(size * price, filters.quote_precision)
    fee = round_half_up(quote * fees.taker, filters.quote_precision)

    _, quote_asset = unpack_symbol(symbol)
    summary.append_position(
        ctx.open_position.close(
            time=candle.time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=quote_asset
            )]
        )
    )

    ctx.quote += quote - fee
    ctx.open_position = None
