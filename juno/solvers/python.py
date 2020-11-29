from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from juno import Advice, Candle, MissedCandlePolicy, OrderException, stop_loss, take_profit
from juno.components import Informant
from juno.statistics import analyse_portfolio
from juno.strategies import Changed, Strategy
from juno.trading import CloseReason, Position, SimulatedPositionMixin, TradingSummary
from juno.utils import unpack_symbol

from .solver import FitnessValues, Solver


@dataclass
class _State:
    summary: TradingSummary
    strategy: Strategy
    quote: Decimal
    stop_loss: stop_loss.StopLoss
    take_profit: take_profit.TakeProfit
    changed: Changed = field(default_factory=lambda: Changed(True))
    open_position: Optional[Position.Open] = None
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None


# We could rename the class to PythonSolver but it's more user-friendly to allow people to just
# specify { "solver": "python" } in config.
class Python(Solver, SimulatedPositionMixin):
    def __init__(self, informant: Informant) -> None:
        self._informant = informant

    @property
    def informant(self) -> Informant:
        return self._informant

    def solve(self, config: Solver.Config) -> FitnessValues:
        summary = self._trade(config)
        portfolio = analyse_portfolio(
            benchmark_g_returns=config.benchmark_g_returns,
            asset_prices=config.fiat_prices,
            trading_summary=summary,
        )
        return FitnessValues.from_trading_summary(summary, portfolio.stats)

    def _trade(self, config: Solver.Config) -> TradingSummary:
        _, quote_asset = unpack_symbol(config.symbol)
        state = _State(
            summary=TradingSummary(
                start=config.candles[0].time,
                quote=config.quote,
                quote_asset=quote_asset,
            ),
            strategy=config.new_strategy(),
            quote=config.quote,
            stop_loss=stop_loss.Legacy(config.stop_loss, config.trail_stop_loss),
            take_profit=take_profit.Legacy(config.take_profit),
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
                if isinstance(state.open_position, Position.OpenLong):
                    self._close_long_position(
                        config, state, state.last_candle, CloseReason.CANCELLED
                    )
                elif isinstance(state.open_position, Position.OpenShort):
                    self._close_short_position(
                        config, state, state.last_candle, CloseReason.CANCELLED
                    )

        except OrderException:
            pass

        state.summary.finish(config.candles[-1].time + config.interval)
        return state.summary

    def _tick(self, config: Solver.Config, state: _State, candle: Candle) -> None:
        state.stop_loss.update(candle)
        state.take_profit.update(candle)
        advice = state.changed.update(state.strategy.update(candle))

        if isinstance(state.open_position, Position.OpenLong):
            if advice in [Advice.SHORT, Advice.LIQUIDATE]:
                self._close_long_position(config, state, candle, CloseReason.STRATEGY)
            elif state.stop_loss.upside_hit:
                self._close_long_position(config, state, candle, CloseReason.STOP_LOSS)
            elif state.take_profit.upside_hit:
                self._close_long_position(config, state, candle, CloseReason.TAKE_PROFIT)
        elif isinstance(state.open_position, Position.OpenShort):
            if advice in [Advice.LONG, Advice.LIQUIDATE]:
                self._close_short_position(config, state, candle, CloseReason.STRATEGY)
            elif state.stop_loss.downside_hit:
                self._close_short_position(config, state, candle, CloseReason.STOP_LOSS)
            elif state.take_profit.downside_hit:
                self._close_short_position(config, state, candle, CloseReason.TAKE_PROFIT)

        if not state.open_position:
            if config.long and advice is Advice.LONG:
                self._open_long_position(config, state, candle)
            elif config.short and advice is Advice.SHORT:
                self._open_short_position(config, state, candle)
            state.stop_loss.clear(candle)
            state.take_profit.clear(candle)

        if not state.first_candle:
            state.first_candle = candle
        state.last_candle = candle

    def _open_long_position(self, config: Solver.Config, state: _State, candle: Candle) -> None:
        position = self.open_simulated_long_position(
            exchange=config.exchange,
            symbol=config.symbol,
            time=candle.time + config.interval,
            price=candle.close,
            quote=state.quote,
            log=False,
        )

        state.quote += position.quote_delta()
        state.open_position = position

    def _close_long_position(
        self, config: Solver.Config, state: _State, candle: Candle, reason: CloseReason
    ) -> None:
        assert isinstance(state.open_position, Position.OpenLong)
        position = self.close_simulated_long_position(
            position=state.open_position,
            time=candle.time + config.interval,
            price=candle.close,
            reason=reason,
            log=False,
        )

        state.quote += position.quote_delta()
        state.open_position = None
        state.summary.append_position(position)

    def _open_short_position(self, config: Solver.Config, state: _State, candle: Candle) -> None:
        position = self.open_simulated_short_position(
            exchange=config.exchange,
            symbol=config.symbol,
            time=candle.time + config.interval,
            price=candle.close,
            collateral=state.quote,
            log=False,
        )

        state.quote += position.quote_delta()
        state.open_position = position

    def _close_short_position(
        self, config: Solver.Config, state: _State, candle: Candle, reason: CloseReason
    ) -> None:
        assert isinstance(state.open_position, Position.OpenShort)
        position = self.close_simulated_short_position(
            position=state.open_position,
            time=candle.time + config.interval,
            price=candle.close,
            reason=reason,
            log=False,
        )

        state.quote += position.quote_delta()
        state.open_position = None
        state.summary.append_position(position)
