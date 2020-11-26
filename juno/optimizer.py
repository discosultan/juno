import asyncio
import logging
import math
import sys
import threading
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from random import Random, randrange
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from deap import base, tools

from juno import (
    Candle, Interval, MissedCandlePolicy, OrderException, Timestamp, stop_loss, take_profit
)
from juno.components import Chandler, Informant, Prices
from juno.constraints import Choice, Constant, Constraint, ConstraintChoice, Uniform
from juno.deap import cx_uniform, ea_mu_plus_lambda, mut_individual
from juno.math import floor_multiple
from juno.solvers import FitnessValues, Individual, Solver
from juno.statistics import AnalysisSummary, Statistics, analyse_benchmark, analyse_portfolio
from juno.strategies import Strategy
from juno.time import strfinterval, strfspan, time_ms
from juno.traders import Basic, BasicConfig
from juno.trading import StartMixin, TradingSummary
from juno.typing import TypeConstructor, map_input_args

_log = logging.getLogger(__name__)

_missed_candle_policy_constraint = Choice([
    MissedCandlePolicy.IGNORE,
    MissedCandlePolicy.RESTART,
    MissedCandlePolicy.LAST,
])
_stop_loss_constraint = ConstraintChoice([
    Constant(Decimal('0.0')),
    Uniform(Decimal('0.0001'), Decimal('0.9999')),
])
_take_profit_constraint = ConstraintChoice([
    Constant(Decimal('0.0')),
    Uniform(Decimal('0.0001'), Decimal('9.9999')),
])
_boolean_constraint = Choice([True, False])


class OptimizationSummary(NamedTuple):
    trading_config: BasicConfig
    trading_summary: TradingSummary
    portfolio_stats: Statistics


@dataclass(frozen=True)
class OptimizerConfig:
    exchange: str
    quote: Decimal
    strategy: TypeConstructor[Strategy]
    symbols: Optional[List[str]] = None
    intervals: Optional[List[Interval]] = None
    start: Optional[Timestamp] = None
    end: Optional[Timestamp] = None
    missed_candle_policy: Optional[MissedCandlePolicy] = MissedCandlePolicy.IGNORE
    stop_loss: Optional[Decimal] = Decimal('0.0')
    trail_stop_loss: Optional[bool] = True
    take_profit: Optional[Decimal] = Decimal('0.0')
    long: Optional[bool] = True
    short: Optional[bool] = False
    population_size: int = 50
    max_generations: int = 1000
    mutation_probability: Decimal = Decimal('0.2')
    seed: Optional[int] = None
    verbose: bool = False
    fiat_exchange: Optional[str] = None
    fiat_asset: str = 'usdt'


@dataclass
class OptimizerState:
    config: OptimizerConfig
    start: Timestamp
    end: Timestamp
    seed: int
    symbols: List[str]
    intervals: List[int]
    generation: int = 0
    summary: Optional[OptimizationSummary] = None
    random_state: Optional[Tuple[int, Tuple[int, ...], None]] = None
    population: Optional[List[Any]] = None


# TODO: Does not support persist/resume. Population not stored/restored properly. Need to store
# fitness + convert raw values to their respective types.
class Optimizer(StartMixin):
    def __init__(
        self,
        solver: Solver,
        chandler: Chandler,
        informant: Informant,
        prices: Prices,
        trader: Basic,
    ) -> None:
        self._solver = solver
        self._chandler = chandler
        self._informant = informant
        self._prices = prices
        self._trader = trader

    @property
    def chandler(self) -> Chandler:
        return self._chandler

    async def initialize(self, config: OptimizerConfig) -> OptimizerState:
        now = time_ms()

        assert not config.end or config.end <= now
        assert not config.start or config.start < now
        assert not config.end or not config.start or config.end > config.start
        assert config.quote > 0
        assert config.symbols is None or len(config.symbols) > 0
        assert config.intervals is None or len(config.intervals) > 0
        assert config.seed is None or config.seed >= 0

        symbols = self._informant.list_symbols(config.exchange, config.symbols)
        intervals = self._informant.list_candle_intervals(config.exchange, config.intervals)

        # We normalize `start` and `end` later to take all potential intervals into account.
        return OptimizerState(
            config=config,
            start=await self.request_start(
                config.start, config.exchange, symbols, intervals
            ),
            end=now if config.end is None else config.end,
            seed=randrange(sys.maxsize) if config.seed is None else config.seed,
            symbols=symbols,
            intervals=intervals,
        )

    async def run(self, state: OptimizerState) -> OptimizationSummary:
        config = state.config
        _log.info(f'randomizer seed ({state.seed})')

        fiat_prices = await self._prices.map_asset_prices(
            exchange=config.exchange,
            # We need BTC prices for benchmark.
            symbols=state.symbols + [f'btc-{config.fiat_asset}'],
            start=state.start,
            end=state.end,
            fiat_asset=config.fiat_asset,
            fiat_exchange=config.fiat_exchange,
        )

        # Fetch candles for backtesting.
        candles = await self.chandler.map_symbol_interval_candles(
            config.exchange, state.symbols, state.intervals, state.start, state.end
        )

        for (s, i), _v in ((k, v) for k, v in candles.items() if len(v) == 0):
            # TODO: Exclude from optimization.
            _log.warning(f'no {s} {strfinterval(i)} candles found between '
                         f'{strfspan(state.start, state.end)}')

        # Prepare benchmark stats.
        benchmark = analyse_benchmark(fiat_prices['btc'])

        # NB! All the built-in algorithms in DEAP use random module directly. This doesn't work for
        # us because we want to be able to use multiple optimizers with different random seeds.
        # Therefore we need to use custom algorithms to support passing in our own `random.Random`.
        random = Random(state.seed)
        if state.random_state:
            random.setstate(state.random_state)

        # Objectives.
        _log.info(f'objectives: {FitnessValues.meta()}')

        toolbox = base.Toolbox()

        # Initialization.
        attrs = [
            _build_attr(state.symbols, Choice(state.symbols), random),
            _build_attr(state.intervals, Choice(state.intervals), random),
            _build_attr(config.missed_candle_policy, _missed_candle_policy_constraint, random),
            _build_attr(config.stop_loss, _stop_loss_constraint, random),
            _build_attr(config.trail_stop_loss, _boolean_constraint, random),
            _build_attr(config.take_profit, _take_profit_constraint, random),
            _build_attr(config.long, _boolean_constraint, random),
            _build_attr(config.short, _boolean_constraint, random),
        ]
        for key, constraint in config.strategy.type_.meta().constraints.items():
            if isinstance(key, str):
                attrs.append(_build_attr(config.strategy.kwargs.get(key), constraint, random))
            else:
                vals = [config.strategy.kwargs.get(sk) for sk in key]
                if all(vals):
                    for val in vals:
                        attrs.append(Constant(val).get)
                elif not any(vals):
                    attrs.append(partial(constraint.random, random))
                else:
                    raise ValueError(f'Either all or none of the attributes must be set: {key}')

        toolbox.register('attributes', lambda: (a() for a in attrs))
        toolbox.register(
            'individual', tools.initIterate, Individual, toolbox.attributes
        )
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)

        # Operators.

        indpb = 1.0 / len(attrs)
        toolbox.register('mate', partial(cx_uniform, random), indpb=indpb)
        toolbox.register('mutate', partial(mut_individual, random), attrs=attrs, indpb=indpb)
        toolbox.register('select', tools.selNSGA2)

        def evaluate(ind: Individual) -> FitnessValues:
            assert state
            return self._solver.solve(
                Solver.Config(
                    fiat_prices=fiat_prices,
                    benchmark_g_returns=benchmark.g_returns,
                    candles=candles[(ind.symbol, ind.interval)],
                    strategy_type=config.strategy.type_,
                    exchange=config.exchange,
                    start=state.start,
                    end=state.end,
                    quote=config.quote,
                    symbol=ind.symbol,
                    interval=ind.interval,
                    missed_candle_policy=ind.missed_candle_policy,
                    stop_loss=ind.stop_loss,
                    trail_stop_loss=ind.trail_stop_loss,
                    take_profit=ind.take_profit,
                    long=ind.long,
                    short=ind.short,
                    strategy_args=ind.strategy_args,
                )
            )

        toolbox.register('evaluate', evaluate)

        toolbox.population_size = config.population_size
        toolbox.max_generations = config.max_generations
        toolbox.mutation_probability = config.mutation_probability

        if state.population is None:
            pop = toolbox.population(n=toolbox.population_size)
            state.population = toolbox.select(pop, len(pop))

        hall_of_fame = tools.HallOfFame(1)

        _log.info('evolving')
        evolve_start = time_ms()

        try:
            cancellation_request = threading.Event()
            cancellation_response = asyncio.Event()
            cancelled_exc = None
            # Returns the final population and logbook with the statistics of the evolution.
            # TODO: Cancelling does not cancel the actual threadpool executor work. See
            # https://gist.github.com/yeraydiazdiaz/b8c059c6dcfaf3255c65806de39175a7
            final_pop, stat = await asyncio.get_running_loop().run_in_executor(
                None, partial(
                    ea_mu_plus_lambda,
                    random=random,
                    population=state.population,
                    toolbox=toolbox,
                    mu=toolbox.population_size,
                    lambda_=toolbox.population_size,
                    cxpb=Decimal('1.0') - toolbox.mutation_probability,
                    mutpb=toolbox.mutation_probability,
                    stats=None,
                    ngen=toolbox.max_generations,
                    halloffame=hall_of_fame,
                    verbose=config.verbose,
                    cancellation_request=cancellation_request,
                    cancellation_response=cancellation_response,
                )
            )

            _log.info(f'evolution finished in {strfinterval(time_ms() - evolve_start)}')
        except asyncio.CancelledError as exc:
            cancelled_exc = exc
            cancellation_request.set()
            await cancellation_response.wait()
        finally:
            state.random_state = random.getstate()  # type: ignore

        best_ind = hall_of_fame[0]
        state.summary = await self._build_summary(state, fiat_prices, benchmark, best_ind)
        self._validate(state, fiat_prices, benchmark, candles, best_ind)

        if cancelled_exc:
            raise cancelled_exc
        return state.summary

    async def _build_summary(
        self,
        state: OptimizerState,
        fiat_prices: Dict[str, List[Decimal]],
        benchmark: AnalysisSummary,
        ind: Individual,
    ) -> OptimizationSummary:
        config = state.config
        _log.info('building trading summary from best result')

        start = floor_multiple(state.start, ind.interval)
        end = floor_multiple(state.end, ind.interval)
        trading_config = BasicConfig(
            exchange=config.exchange,
            symbol=ind.symbol,
            interval=ind.interval,
            start=start,
            end=end,
            quote=config.quote,
            missed_candle_policy=ind.missed_candle_policy,
            stop_loss=_stop_loss(ind.stop_loss, ind.trail_stop_loss),
            take_profit=_take_profit(ind.take_profit),
            long=ind.long,
            short=ind.short,
            adjust_start=False,
            strategy=TypeConstructor.from_type(
                config.strategy.type_,
                **map_input_args(config.strategy.type_.__init__, ind.strategy_args),
            ),
        )

        trader_state = await self._trader.initialize(trading_config)
        try:
            await self._trader.run(trader_state)
        except OrderException as e:
            _log.warning(f'trader stopped with exception: {e}')
        assert trader_state.summary
        portfolio_summary = analyse_portfolio(
            benchmark.g_returns, fiat_prices, trader_state.summary
        )

        return OptimizationSummary(
            trading_config=trading_config,
            trading_summary=trader_state.summary,
            portfolio_stats=portfolio_summary.stats,
        )

    def _validate(
        self,
        state: OptimizerState,
        fiat_prices: Dict[str, List[Decimal]],
        benchmark: AnalysisSummary,
        candles: Dict[Tuple[str, int], List[Candle]],
        ind: Individual,
    ) -> None:
        assert state.summary
        # Validate trader backtest result with solver result.
        solver_name = type(self._solver).__name__.lower()
        _log.info(f'validating {solver_name} fitness values against actual trader')

        trader_fitness_values = FitnessValues.from_trading_summary(
            state.summary.trading_summary, state.summary.portfolio_stats
        )

        if not _isclose(trader_fitness_values, ind.fitness.values):
            raise Exception(
                f'Optimizer results differ between trader and {solver_name} solver.\nTrading '
                f'config: {state.summary.trading_config}\nTrader result: {trader_fitness_values}\n'
                f'Solver result: {ind.fitness.values}'
            )


def _build_attr(target: Optional[Any], constraint: Constraint, random: Any) -> Callable[[], Any]:
    if target is None or isinstance(target, list) and len(target) > 1:
        return partial(constraint.random, random)
    else:
        value = target[0] if isinstance(target, list) else target
        return Constant(value).get


def _isclose(a: Tuple[Any, ...], b: Tuple[Any, ...]) -> bool:
    isclose = True
    for aval, bval in zip(a, b):
        if isinstance(aval, Decimal):
            isclose = isclose and math.isclose(aval, bval, abs_tol=Decimal('1e-6'))
        elif isinstance(aval, float):
            isclose = isclose and math.isclose(aval, bval, abs_tol=1e-6)
        else:
            isclose = isclose and aval == bval
    return isclose


def _stop_loss(
    threshold: Decimal, trail: bool
) -> Optional[TypeConstructor[stop_loss.StopLoss]]:
    if threshold == 0:
        return None
    if trail:
        return TypeConstructor.from_type(stop_loss.Trailing, threshold=threshold)
    return TypeConstructor.from_type(stop_loss.Basic, threshold=threshold)


def _take_profit(
    threshold: Decimal
) -> Optional[TypeConstructor[take_profit.TakeProfit]]:
    if threshold == 0:
        return None
    return TypeConstructor.from_type(take_profit.Basic, threshold=threshold)
