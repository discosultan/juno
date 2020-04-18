from decimal import Decimal
from typing import Optional

from juno import Advice, Candle, Fill, OrderException
from juno.math import ceil_multiple, round_half_up
from juno.strategies import Changed, Strategy
from juno.time import HOUR_MS
from juno.trading import (
    MissedCandlePolicy, OpenLongPosition, OpenShortPosition, TradingSummary, analyse_portfolio
)

from .solver import Solver, SolverResult


class _State:
    def __init__(self, summary: TradingSummary, strategy: Strategy, quote: Decimal) -> None:
        self.summary = summary
        self.strategy = strategy
        self.changed = Changed(True)
        self.quote = quote
        self.open_long_position: Optional[OpenLongPosition] = None
        self.open_short_position: Optional[OpenShortPosition] = None
        self.first_candle: Optional[Candle] = None
        self.last_candle: Optional[Candle] = None
        self.highest_close_since_position = Decimal('0.0')
        self.lowest_close_since_position = Decimal('Inf')


# We could rename the class to PythonSolver but it's more user-friendly to allow people to just
# specify { "solver": "python" } in config.
class Python(Solver):
    def solve(self, config: Solver.Config) -> SolverResult:
        summary = _trade(config)
        portfolio = analyse_portfolio(
            config.benchmark_g_returns, config.fiat_daily_prices, summary
        )
        return SolverResult.from_trading_summary(summary, portfolio.stats)


def _trade(config: Solver.Config) -> TradingSummary:
    state = _State(
        TradingSummary(start=config.candles[0].time, quote=config.quote),
        config.new_strategy(),
        config.quote,
    )
    try:
        i = 0
        while True:
            restart = False

            for candle in config.candles[i:]:
                i += 1
                if not candle.closed:
                    continue

                # TODO: python 3.8 assignment expression
                if (
                    config.missed_candle_policy is not MissedCandlePolicy.IGNORE
                    and state.last_candle
                    and candle.time - state.last_candle.time >= config.interval * 2
                ):
                    if config.missed_candle_policy is MissedCandlePolicy.RESTART:
                        restart = True
                        state.strategy = config.new_strategy()
                    elif config.missed_candle_policy is MissedCandlePolicy.LAST:
                        num_missed = (candle.time - state.last_candle.time) // config.interval - 1
                        last_candle = state.last_candle
                        for i in range(1, num_missed + 1):
                            missed_candle = Candle(
                                time=last_candle.time + i * config.interval,
                                open=last_candle.open,
                                high=last_candle.high,
                                low=last_candle.low,
                                close=last_candle.close,
                                volume=last_candle.volume,
                                closed=last_candle.closed
                            )
                            _tick(config, state, missed_candle)
                    else:
                        raise NotImplementedError()

                _tick(config, state, candle)

                if restart:
                    break

            if not restart:
                break

        if state.last_candle:
            if state.open_long_position:
                _close_long_position(config, state, state.last_candle)
            if state.open_short_position:
                _close_short_position(config, state, state.last_candle)

    except OrderException:
        pass

    state.summary.finish(config.candles[-1].time + config.interval)
    return state.summary


def _tick(config: Solver.Config, state: _State, candle: Candle) -> None:
    advice = state.changed.update(state.strategy.update(candle))

    if state.open_long_position:
        if advice in [Advice.SHORT, Advice.LIQUIDATE]:
            _close_long_position(config, state, candle)
        elif config.trailing_stop:
            state.highest_close_since_position = max(
                state.highest_close_since_position, candle.close
            )
            target = state.highest_close_since_position * config.upside_trailing_factor
            if candle.close <= target:
                _close_long_position(config, state, candle)
    elif state.open_short_position:
        if advice in [Advice.LONG, Advice.LIQUIDATE]:
            _close_short_position(config, state, candle)
        elif config.trailing_stop:
            state.lowest_close_since_position = min(
                state.lowest_close_since_position, candle.close
            )
            target = state.lowest_close_since_position * config.downside_trailing_factor
            if candle.close >= target:
                _close_short_position(config, state, candle)

    if not state.open_long_position and not state.open_short_position:
        if config.long and advice is Advice.LONG:
            _open_long_position(config, state, candle)
            state.highest_close_since_position = candle.close
        elif config.short and advice is Advice.SHORT:
            _open_short_position(config, state, candle)
            state.lowest_close_since_position = candle.close

    if not state.first_candle:
        state.first_candle = candle
    state.last_candle = candle


def _open_long_position(config: Solver.Config, state: _State, candle: Candle) -> None:
    price = candle.close

    size = config.filters.size.round_down(state.quote / price)
    if size == 0:
        raise OrderException()

    quote = round_half_up(size * price, config.filters.quote_precision)
    fee = round_half_up(size * config.fees.taker, config.filters.base_precision)

    state.open_long_position = OpenLongPosition(
        symbol=config.symbol,
        time=candle.time,
        fills=[Fill(
            price=price, size=size, quote=quote, fee=fee, fee_asset=config.base_asset
        )],
    )

    state.quote -= quote


def _close_long_position(config: Solver.Config, state: _State, candle: Candle) -> None:
    assert state.open_long_position

    price = candle.close

    size = config.filters.size.round_down(state.open_long_position.base_gain)

    quote = round_half_up(size * price, config.filters.quote_precision)
    fee = round_half_up(quote * config.fees.taker, config.filters.quote_precision)

    state.summary.append_position(
        state.open_long_position.close(
            time=candle.time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=config.quote_asset
            )]
        )
    )

    state.quote += quote - fee
    state.open_long_position = None


def _open_short_position(config: Solver.Config, state: _State, candle: Candle) -> None:
    price = candle.close

    collateral_size = config.filters.size.round_down(state.quote / price)
    if collateral_size == 0:
        raise OrderException()
    borrowed = collateral_size * (config.margin_multiplier - 1)

    quote = round_half_up(price * borrowed, config.filters.quote_precision)
    fee = round_half_up(quote * config.fees.taker, config.filters.quote_precision)

    state.open_short_position = OpenShortPosition(
        symbol=config.symbol,
        collateral=state.quote,
        borrowed=borrowed,
        time=candle.time,
        fills=[Fill(
            price=price, size=borrowed, quote=quote, fee=fee, fee_asset=config.quote_asset
        )],
    )

    state.quote += quote - fee


def _close_short_position(config: Solver.Config, state: _State, candle: Candle) -> None:
    assert state.open_short_position

    price = candle.close
    borrowed = state.open_short_position.borrowed

    duration = ceil_multiple(candle.time - state.open_short_position.time, HOUR_MS) // HOUR_MS
    interest = duration * config.borrow_info.hourly_interest_rate

    size = borrowed + interest
    quote = round_half_up(price * size, config.filters.quote_precision)
    fee = round_half_up(size * config.fees.taker, config.filters.base_precision)
    size += fee

    position = state.open_short_position.close(
        time=candle.time,
        interest=interest,
        fills=[Fill(
            price=price, size=size, quote=quote, fee=fee, fee_asset=config.base_asset
        )],
    )

    state.quote -= quote

    state.open_short_position = None
    state.summary.append_position(position)
