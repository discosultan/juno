from decimal import Decimal
from typing import Optional

from juno import Advice, Candle, Fill, MissedCandlePolicy, OrderException
from juno.components import Informant
from juno.statistics import analyse_portfolio
from juno.strategies import Changed, Strategy
from juno.trading import CloseReason, Position, SimulatedPositionMixin, TradingSummary

from .solver import Solver, SolverResult


class _State:
    def __init__(self, summary: TradingSummary, strategy: Strategy, quote: Decimal) -> None:
        self.summary = summary
        self.strategy = strategy
        self.changed = Changed(True)
        self.quote = quote
        self.open_long_position: Optional[Position.OpenLong] = None
        self.open_short_position: Optional[Position.OpenShort] = None
        self.first_candle: Optional[Candle] = None
        self.last_candle: Optional[Candle] = None
        self.highest_close_since_position = Decimal('0.0')
        self.lowest_close_since_position = Decimal('Inf')


# We could rename the class to PythonSolver but it's more user-friendly to allow people to just
# specify { "solver": "python" } in config.
class Python(Solver, SimulatedPositionMixin):
    def __init__(self, informant: Informant) -> None:
        self._informant = informant

    @property
    def informant(self) -> Informant:
        return self._informant

    def solve(self, config: Solver.Config) -> SolverResult:
        summary = self._trade(config)
        portfolio = analyse_portfolio(
            config.benchmark_g_returns, config.fiat_daily_prices, summary
        )
        return SolverResult.from_trading_summary(summary, portfolio.stats)

    def _trade(self, config: Solver.Config) -> TradingSummary:
        state = _State(
            TradingSummary(
                start=config.candles[0].time,
                quote=config.quote,
                quote_asset=config.quote_asset,
            ),
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

                    if (
                        config.missed_candle_policy is not MissedCandlePolicy.IGNORE
                        and (last_candle := state.last_candle)
                        and (time_diff := (candle.time - last_candle.time)) >= config.interval * 2
                    ):
                        if config.missed_candle_policy is MissedCandlePolicy.RESTART:
                            restart = True
                            state.strategy = config.new_strategy()
                        elif config.missed_candle_policy is MissedCandlePolicy.LAST:
                            num_missed = time_diff // config.interval - 1
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
                                self._tick(config, state, missed_candle)
                        else:
                            raise NotImplementedError()

                    self._tick(config, state, candle)

                    if restart:
                        break

                if not restart:
                    break

            if state.last_candle:
                if state.open_long_position:
                    self._close_long_position(
                        config, state, state.last_candle, CloseReason.CANCELLED
                    )
                if state.open_short_position:
                    self._close_short_position(
                        config, state, state.last_candle, CloseReason.CANCELLED
                    )

        except OrderException:
            pass

        state.summary.finish(config.candles[-1].time + config.interval)
        return state.summary

    def _tick(self, config: Solver.Config, state: _State, candle: Candle) -> None:
        advice = state.changed.update(state.strategy.update(candle))

        if state.open_long_position:
            if advice in [Advice.SHORT, Advice.LIQUIDATE]:
                self._close_long_position(config, state, candle, CloseReason.STRATEGY)
            elif config.trailing_stop:
                state.highest_close_since_position = max(
                    state.highest_close_since_position, candle.close
                )
                target = state.highest_close_since_position * config.upside_trailing_factor
                if candle.close <= target:
                    self._close_long_position(config, state, candle, CloseReason.TRAILING_STOP)
        elif state.open_short_position:
            if advice in [Advice.LONG, Advice.LIQUIDATE]:
                self._close_short_position(config, state, candle, CloseReason.STRATEGY)
            elif config.trailing_stop:
                state.lowest_close_since_position = min(
                    state.lowest_close_since_position, candle.close
                )
                target = state.lowest_close_since_position * config.downside_trailing_factor
                if candle.close >= target:
                    self._close_short_position(config, state, candle, CloseReason.TRAILING_STOP)

        if not state.open_long_position and not state.open_short_position:
            if config.long and advice is Advice.LONG:
                self._open_long_position(config, state, candle)
                state.highest_close_since_position = candle.close
            elif config.short and advice is Advice.SHORT:
                self._open_short_position(config, state, candle)
                state.lowest_close_since_position = candle.close

        if not state.first_candle:
            state.first_candle = candle
        state.last_candle = candle

    def _open_long_position(self, config: Solver.Config, state: _State, candle: Candle) -> None:
        position = self.open_simulated_long_position(
            exchange=config.exchange,
            symbol=config.symbol,
            time=candle.time,
            price=candle.close,
            quote=state.quote,
        )

        state.quote -= Fill.total_quote(position.fills)
        state.open_long_position = position

    def _close_long_position(
        self, config: Solver.Config, state: _State, candle: Candle, reason: CloseReason
    ) -> None:
        assert state.open_long_position
        position = self.close_simulated_long_position(
            position=state.open_long_position,
            time=candle.time,
            price=candle.close,
            reason=reason,
        )

        state.quote += (
            Fill.total_quote(position.close_fills) - Fill.total_fee(position.close_fills)
        )
        state.open_long_position = None
        state.summary.append_position(position)

    def _open_short_position(self, config: Solver.Config, state: _State, candle: Candle) -> None:
        position = self.open_simulated_short_position(
            exchange=config.exchange,
            symbol=config.symbol,
            time=candle.time,
            price=candle.close,
            collateral=state.quote,
        )

        state.quote += Fill.total_quote(position.fills) - Fill.total_fee(position.fills)
        state.open_short_position = position

    def _close_short_position(
        self, config: Solver.Config, state: _State, candle: Candle, reason: CloseReason
    ) -> None:
        assert state.open_short_position
        position = self.close_simulated_short_position(
            position=state.open_short_position,
            time=candle.time,
            price=candle.close,
            reason=reason,
        )

        state.quote -= Fill.total_quote(position.close_fills)
        state.open_short_position = None
        state.summary.append_position(position)
