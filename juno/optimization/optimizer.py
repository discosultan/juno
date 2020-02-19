import asyncio
import logging
import math
import sys
from decimal import Decimal
from functools import partial
from itertools import product
from random import Random, randrange
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Type

from deap import base, creator, tools

from juno import Candle, InsufficientBalance, Interval, Timestamp
from juno.components import Chandler, Informant, Prices
from juno.math import Choice, Constant, Constraint, ConstraintChoice, Uniform, floor_multiple
from juno.strategies import Strategy
from juno.time import strfinterval, strfspan, time_ms
from juno.trading import (
    MissedCandlePolicy, Statistics, Trader, TradingSummary, analyse_benchmark, analyse_portfolio
)
from juno.typing import map_input_args
from juno.utils import asdict, flatten, unpack_symbol

from .deap import cx_uniform, ea_mu_plus_lambda, mut_individual
from .solver import Solver, SolverResult

_log = logging.getLogger(__name__)

_missed_candle_policy_constraint = Choice([
    MissedCandlePolicy.IGNORE,
    MissedCandlePolicy.RESTART,
    MissedCandlePolicy.LAST,
])
_trailing_stop_constraint = ConstraintChoice([
    Constant(Decimal('0.0')),
    Uniform(Decimal('0.0001'), Decimal('0.9999')),
])


class TradingConfig(NamedTuple):
    exchange: str
    symbol: str
    interval: Interval
    start: Timestamp
    end: Timestamp
    quote: Decimal
    missed_candle_policy: MissedCandlePolicy
    trailing_stop: Decimal
    adjust_start: bool
    strategy_type: Type[Strategy]
    strategy_kwargs: Dict[str, Any]


class OptimizationSummary(NamedTuple):
    trading_config: TradingConfig
    trading_summary: TradingSummary
    portfolio_stats: Statistics


class Optimizer:
    def __init__(
        self,
        solver: Solver,
        chandler: Chandler,
        informant: Informant,
        prices: Prices,
        trader: Trader,
    ) -> None:
        self._solver = solver
        self._chandler = chandler
        self._informant = informant
        self._prices = prices
        self._trader = trader

    async def run(
        self,
        exchange: str,
        start: Timestamp,
        quote: Decimal,
        strategy_type: Type[Strategy],
        symbols: Optional[List[str]] = None,
        intervals: Optional[List[Interval]] = None,
        end: Optional[Timestamp] = None,
        missed_candle_policy: Optional[MissedCandlePolicy] = MissedCandlePolicy.IGNORE,
        trailing_stop: Optional[Decimal] = Decimal('0.0'),
        population_size: int = 50,
        max_generations: int = 1000,
        mutation_probability: Decimal = Decimal('0.2'),
        seed: Optional[int] = None,
        verbose: bool = False,
    ) -> OptimizationSummary:
        now = time_ms()

        if end is None:
            end = now

        # We normalize `start` and `end` later to take all potential intervals into account.

        assert end <= now
        assert end > start
        assert quote > 0

        assert symbols is None or len(symbols) > 0
        assert intervals is None or len(intervals) > 0

        if seed is None:
            seed = randrange(sys.maxsize)

        # TODO: Use _Context similar to trader?

        _log.info(f'randomizer seed ({seed})')

        symbols = self._informant.list_symbols(exchange, symbols)
        intervals = self._informant.list_candle_intervals(exchange, intervals)

        fiat_daily_prices = await self._prices.map_fiat_daily_prices(
            {a for s in symbols for a in unpack_symbol(s)}, start, end
        )

        candles: Dict[Tuple[str, int], List[Candle]] = {}

        async def assign(symbol: str, interval: int) -> None:
            assert end
            candles[(symbol, interval)] = await self._chandler.list_candles(
                exchange, symbol, interval, floor_multiple(start, interval),
                floor_multiple(end, interval)
            )

        # Fetch candles for backtesting.
        await asyncio.gather(*(assign(s, i) for s, i in product(symbols, intervals)))

        for (s, i), _v in ((k, v) for k, v in candles.items() if len(v) == 0):
            # TODO: Exclude from optimization.
            _log.warning(f'no {s} {strfinterval(i)} candles found between '
                         f'{strfspan(start, end)}')

        fees_filters = {s: self._informant.get_fees_filters(exchange, s) for s in symbols}

        # Prepare benchmark stats.
        benchmark = analyse_benchmark(fiat_daily_prices['btc'])

        # NB! All the built-in algorithms in DEAP use random module directly. This doesn't work for
        # us because we want to be able to use multiple optimizers with different random seeds.
        # Therefore we need to use custom algorithms to support passing in our own `random.Random`.
        random = Random(seed)

        # Objectives.
        objectives = SolverResult.meta()
        _log.info(f'objectives: {objectives}')

        # Creator generated instances are global!
        if not getattr(creator, 'FitnessMulti', None):
            creator.create('FitnessMulti', base.Fitness, weights=list(objectives.values()))
            creator.create('Individual', list, fitness=creator.FitnessMulti)

        toolbox = base.Toolbox()

        # Initialization.
        attrs = [
            _build_attr(symbols, Choice(symbols), random),
            _build_attr(intervals, Choice(intervals), random),
            _build_attr(missed_candle_policy, _missed_candle_policy_constraint, random),
            _build_attr(trailing_stop, _trailing_stop_constraint, random),
            *(partial(c.random, random) for c in strategy_type.meta.constraints.values())
        ]
        toolbox.register('strategy_args', lambda: (a() for a in attrs))
        toolbox.register(
            'individual', tools.initIterate, creator.Individual, toolbox.strategy_args
        )
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)

        # Operators.

        indpb = 1.0 / len(attrs)
        toolbox.register('mate', cx_uniform(random), indpb=indpb)
        toolbox.register('mutate', mut_individual(random), attrs=attrs, indpb=indpb)
        toolbox.register('select', tools.selNSGA2)

        def evaluate(ind: List[Any]) -> SolverResult:
            return self._solver.solve(
                fiat_daily_prices,
                benchmark.g_returns,
                strategy_type,
                start,
                end,
                quote,
                candles[(ind[0], ind[1])],
                *fees_filters[ind[0]],
                *flatten(ind)
            )

        toolbox.register('evaluate', evaluate)

        toolbox.population_size = population_size
        toolbox.max_generations = max_generations
        toolbox.mutation_probability = mutation_probability

        pop = toolbox.population(n=toolbox.population_size)
        pop = toolbox.select(pop, len(pop))

        hall = tools.HallOfFame(1)

        _log.info('evolving')
        evolve_start = time_ms()

        # Returns the final population and logbook with the statistics of the evolution.
        final_pop, stat = await asyncio.get_running_loop().run_in_executor(
            None, partial(
                ea_mu_plus_lambda(random),
                population=pop,
                toolbox=toolbox,
                mu=toolbox.population_size,
                lambda_=toolbox.population_size,
                cxpb=Decimal('1.0') - toolbox.mutation_probability,
                mutpb=toolbox.mutation_probability,
                stats=None,
                ngen=toolbox.max_generations,
                halloffame=hall,
                verbose=verbose,
            )
        )

        _log.info(f'evolution finished in {strfinterval(time_ms() - evolve_start)}')

        best_args = list(flatten(hall[0]))
        best_result = self._solver.solve(
            fiat_daily_prices,
            benchmark.g_returns,
            strategy_type,
            start,
            end,
            quote,
            candles[(best_args[0], best_args[1])],
            *fees_filters[best_args[0]],
            *best_args
        )

        start = floor_multiple(start, best_args[1])
        trading_config = TradingConfig(
            exchange=exchange,
            symbol=best_args[0],
            interval=best_args[1],
            start=start,
            end=floor_multiple(end, best_args[1]),
            quote=quote,
            missed_candle_policy=best_args[2],
            trailing_stop=best_args[3],
            adjust_start=False,
            strategy_type=strategy_type,
            strategy_kwargs=map_input_args(strategy_type.__init__, best_args[4:])
        )

        trading_summary = TradingSummary(start=start, quote=quote)
        try:
            await self._trader.run(summary=trading_summary, **trading_config._asdict())
        except InsufficientBalance:
            pass
        portfolio_summary = analyse_portfolio(
            benchmark.g_returns, fiat_daily_prices, trading_summary
        )

        optimization_summary = OptimizationSummary(
            trading_config=trading_config,
            trading_summary=trading_summary,
            portfolio_stats=portfolio_summary.stats
        )

        await self._validate(optimization_summary, best_result)

        return optimization_summary

    async def _validate(
        self, optimization_summary: OptimizationSummary, solver_result: SolverResult,
    ) -> None:
        # Validate trader backtest result with solver result.
        solver_name = type(self._solver).__name__.lower()
        _log.info(
            f'validating {solver_name} solver result with best args against actual trader'
        )

        trader_result = SolverResult.from_trading_summary(
            optimization_summary.trading_summary, optimization_summary.portfolio_stats
        )

        if not _isclose(trader_result, solver_result):
            raise Exception(
                f'Optimizer results differ between trader and {solver_name} solver.\nTrading '
                f'config: {optimization_summary.trading_config}\nTrader result: '
                f'{asdict(trader_result)}\nSolver result: {(solver_result)}'
            )


def _build_attr(target: Optional[Any], constraint: Constraint, random: Any) -> Any:
    if target is None or isinstance(target, list) and len(target) > 1:
        def get_random() -> Any:
            return constraint.random(random)  # type: ignore
        return get_random
    else:
        value = target[0] if isinstance(target, list) else target

        def get_constant() -> Any:
            return value
        return get_constant


def _isclose(a: Tuple[Any, ...], b: Tuple[Any, ...]) -> bool:
    isclose = True
    for aval, bval in zip(a, b):
        if isinstance(aval, Decimal):
            isclose = isclose and math.isclose(aval, bval, rel_tol=Decimal('1e-7'))
        elif isinstance(aval, float):
            isclose = isclose and math.isclose(aval, bval, rel_tol=1e-7)
        else:
            isclose = isclose and aval == bval
    return isclose
