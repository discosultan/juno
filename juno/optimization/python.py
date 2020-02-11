from decimal import Decimal
from typing import Any, Dict, List, Type

from juno import Advice, Candle, Fill, InsufficientBalance, Interval, Timestamp
from juno.components import Informant
from juno.math import round_half_up
from juno.strategies import Strategy
from juno.trading import (
    MissedCandlePolicy, Position, Statistics, TradingContext, TradingResult,
    get_portfolio_statistics
)

from .solver import Solver, SolverResult


# We could rename the class to PythonSolver but it's more user-friendly to allow people to just
# specify { "solver": "python" } in config.
class Python(Solver):
    def __init__(self, informant: Informant) -> None:
        self.informant = informant

    def solve(
        self,
        fiat_daily_prices: Dict[str, List[Decimal]],
        benchmark_stats: Statistics,
        strategy_type: Type[Strategy],
        start: Timestamp,
        end: Timestamp,
        quote: Decimal,
        candles: List[Candle],
        exchange: str,
        symbol: str,
        interval: Interval,
        missed_candle_policy: MissedCandlePolicy,
        trailing_stop: Decimal,
        *args: Any,
    ) -> SolverResult:
        trading_result = self._trade(
            strategy_type,
            quote,
            candles,
            exchange,
            symbol,
            interval,
            missed_candle_policy,
            trailing_stop,
            *args,
        )

        portfolio_stats = get_portfolio_statistics(
            benchmark_stats, fiat_daily_prices, trading_result
        )

        return SolverResult.from_trading_result(trading_result, portfolio_stats)

    def _trade(
        self,
        strategy_type: Type[Strategy],
        quote: Decimal,
        candles: List[Candle],
        exchange: str,
        symbol: str,
        interval: Interval,
        missed_candle_policy: MissedCandlePolicy,
        trailing_stop: Decimal,
        *args: Any,
    ):
        ctx = TradingContext(
            strategy=strategy_type(*args),
            start=candles[0].time,
            quote=quote,
            exchange=exchange,
            symbol=symbol,
            trailing_stop=trailing_stop,
            result=TradingResult(start=candles[0].time, quote=quote)
        )
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
                                self._tick(ctx, missed_candle)
                        else:
                            raise NotImplementedError()

                    self._tick(ctx, candle)

                    if restart:
                        break

                if not restart:
                    break

            if ctx.last_candle and ctx.open_position:
                self._close_position(ctx, ctx.last_candle)
        except InsufficientBalance:
            pass

        ctx.result.finish(candles[-1].time + interval)
        return ctx.result

    def _tick(self, ctx: TradingContext, candle: Candle) -> None:
        ctx.strategy.update(candle)
        advice = ctx.strategy.advice

        if not ctx.open_position and advice is Advice.BUY:
            self._try_open_position(ctx, candle)
            ctx.highest_close_since_position = candle.close
        elif ctx.open_position and advice is Advice.SELL:
            self._close_position(ctx, candle)
        elif ctx.trailing_stop != 0 and ctx.open_position:
            ctx.highest_close_since_position = max(ctx.highest_close_since_position, candle.close)
            trailing_factor = 1 - ctx.trailing_stop
            if candle.close <= ctx.highest_close_since_position * trailing_factor:
                self._close_position(ctx, candle)

        if not ctx.first_candle:
            ctx.first_candle = candle
        ctx.last_candle = candle

    def _try_open_position(self, ctx: TradingContext, candle: Candle) -> None:
        fees, filters = self.informant.get_fees_filters(ctx.exchange, ctx.symbol)

        price = candle.close

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

    def _close_position(self, ctx: TradingContext, candle: Candle) -> None:
        pos = ctx.open_position
        assert pos

        fees, filters = self.informant.get_fees_filters(ctx.exchange, ctx.symbol)
        price = candle.close

        size = filters.size.round_down(pos.base_gain)

        quote = size * price
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        pos.close(
            time=candle.time,
            fills=[Fill(price=price, size=size, fee=fee, fee_asset=ctx.quote_asset)]
        )
        ctx.result.append_position(pos)

        ctx.quote += quote - fee

        ctx.open_position = None
