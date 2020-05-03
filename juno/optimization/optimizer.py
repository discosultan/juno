import asyncio
import logging
import math
import sys
import threading
from decimal import Decimal
from functools import partial
from itertools import product
from random import Random, randrange
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from deap import base, creator, tools

from juno import Candle, Interval, OrderException, Timestamp, strategies
from juno.components import Chandler, Historian, Informant, Prices
from juno.itertools import flatten
from juno.math import Choice, Constant, Constraint, ConstraintChoice, Uniform, floor_multiple
from juno.modules import get_module_type
from juno.time import strfinterval, strfspan, time_ms
from juno.trading import (
    MissedCandlePolicy, Statistics, Trader, TradingSummary, analyse_benchmark, analyse_portfolio
)
from juno.typing import map_input_args
from juno.utils import unpack_symbol

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
_boolean_constraint = Choice([True, False])


class OptimizationRecord(NamedTuple):
    trading_config: Trader.Config
    trading_summary: TradingSummary
    portfolio_stats: Statistics


class OptimizationSummary:
    best: List[OptimizationRecord] = []
    population: Optional[List[Any]] = None


class Optimizer:
    def __init__(
        self,
        solver: Solver,
        chandler: Chandler,
        informant: Informant,
        prices: Prices,
        trader: Trader,
        historian: Historian,
    ) -> None:
        self._solver = solver
        self._chandler = chandler
        self._informant = informant
        self._prices = prices
        self._trader = trader
        self._historian = historian

    async def run(
        self,
        exchange: str,
        quote: Decimal,
        strategy: str,
        symbols: Optional[List[str]] = None,
        intervals: Optional[List[Interval]] = None,
        start: Optional[Timestamp] = None,
        end: Optional[Timestamp] = None,
        missed_candle_policy: Optional[MissedCandlePolicy] = MissedCandlePolicy.IGNORE,
        trailing_stop: Optional[Decimal] = Decimal('0.0'),
        long: Optional[bool] = True,
        short: Optional[bool] = False,
        population_size: int = 50,
        max_generations: int = 1000,
        mutation_probability: Decimal = Decimal('0.2'),
        seed: Optional[int] = None,
        verbose: bool = False,
        summary: Optional[OptimizationSummary] = None,
    ) -> OptimizationSummary:
        now = time_ms()

        assert not end or end <= now
        assert not start or start < now
        assert not end or not start or end > start
        assert quote > 0
        assert symbols is None or len(symbols) > 0
        assert intervals is None or len(intervals) > 0

        symbols = self._informant.list_symbols(exchange, symbols)
        intervals = self._informant.list_candle_intervals(exchange, intervals)

        if start is None:
            # Pick latest time of all available symbol interval combinations so that optimization
            # period would be same in all cases.
            first_candles = await asyncio.gather(
                *(
                    self._historian.find_first_candle(exchange, s, i)
                    for s, i in product(symbols, intervals)
                )
            )
            start = max(first_candles, key=lambda c: c.time).time

        if end is None:
            end = now

        # We normalize `start` and `end` later to take all potential intervals into account.

        strategy_type = get_module_type(strategies, strategy)

        if seed is None:
            seed = randrange(sys.maxsize)

        _log.info(f'randomizer seed ({seed})')

        summary = summary or OptimizationSummary()

        fiat_daily_prices = await self._prices.map_fiat_daily_prices(
            exchange, {a for s in symbols for a in unpack_symbol(s)}, start, end
        )

        candles: Dict[Tuple[str, int], List[Candle]] = {}

        async def assign(symbol: str, interval: int) -> None:
            assert start is not None and end is not None
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
            _build_attr(long, _boolean_constraint, random),
            _build_attr(short, _boolean_constraint, random),
            *(partial(c.random, random) for c in strategy_type.meta().constraints.values())
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
                Solver.Config(
                    fiat_daily_prices=fiat_daily_prices,
                    benchmark_g_returns=benchmark.g_returns,
                    candles=candles[(ind[0], ind[1])],
                    strategy_type=strategy_type,
                    exchange=exchange,
                    start=start,
                    end=end,
                    quote=quote,
                    symbol=ind[0],
                    interval=ind[1],
                    missed_candle_policy=ind[2],
                    trailing_stop=ind[3],
                    long=ind[4],
                    short=ind[5],
                    strategy_args=list(flatten(ind[6:])),
                )
            )

        toolbox.register('evaluate', evaluate)

        toolbox.population_size = population_size
        toolbox.max_generations = max_generations
        toolbox.mutation_probability = mutation_probability

        if summary.population is None:
            pop = toolbox.population(n=toolbox.population_size)
            summary.population = toolbox.select(pop, len(pop))

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
                    ea_mu_plus_lambda(random),
                    population=summary.population,
                    toolbox=toolbox,
                    mu=toolbox.population_size,
                    lambda_=toolbox.population_size,
                    cxpb=Decimal('1.0') - toolbox.mutation_probability,
                    mutpb=toolbox.mutation_probability,
                    stats=None,
                    ngen=toolbox.max_generations,
                    halloffame=hall_of_fame,
                    verbose=verbose,
                    cancellation_request=cancellation_request,
                    cancellation_response=cancellation_response,
                )
            )

            _log.info(f'evolution finished in {strfinterval(time_ms() - evolve_start)}')
        except asyncio.CancelledError as exc:
            cancelled_exc = exc
            cancellation_request.set()
            await cancellation_response.wait()

        best_args = list(flatten(hall_of_fame[0]))

        start = floor_multiple(start, best_args[1])
        trading_config = Trader.Config(
            exchange=exchange,
            symbol=best_args[0],
            interval=best_args[1],
            start=start,
            end=floor_multiple(end, best_args[1]),
            quote=quote,
            missed_candle_policy=best_args[2],
            trailing_stop=best_args[3],
            long=best_args[4],
            short=best_args[5],
            adjust_start=False,
            strategy=strategy,
            strategy_kwargs=map_input_args(strategy_type.__init__, best_args[6:]),
        )

        state: Trader.State[Any] = Trader.State()
        try:
            await self._trader.run(trading_config, state)
        except OrderException:
            pass
        assert state.summary
        portfolio_summary = analyse_portfolio(
            benchmark.g_returns, fiat_daily_prices, state.summary
        )

        best_individual = OptimizationRecord(
            trading_config=trading_config,
            trading_summary=state.summary,
            portfolio_stats=portfolio_summary.stats,
        )
        summary.best.append(best_individual)

        # Validate trader backtest result with solver result.
        solver_name = type(self._solver).__name__.lower()
        _log.info(
            f'validating {solver_name} solver result with best args against actual trader'
        )

        solver_result = self._solver.solve(
            Solver.Config(
                fiat_daily_prices=fiat_daily_prices,
                benchmark_g_returns=benchmark.g_returns,
                candles=candles[(best_args[0], best_args[1])],
                strategy_type=strategy_type,
                exchange=exchange,
                start=start,
                end=end,
                quote=quote,
                symbol=best_args[0],
                interval=best_args[1],
                missed_candle_policy=best_args[2],
                trailing_stop=best_args[3],
                long=best_args[4],
                short=best_args[5],
                strategy_args=best_args[6:],
            )
        )

        trader_result = SolverResult.from_trading_summary(
            best_individual.trading_summary, best_individual.portfolio_stats
        )

        if not _isclose(trader_result, solver_result):
            raise Exception(
                f'Optimizer results differ between trader and {solver_name} solver.\nTrading '
                f'config: {best_individual.trading_config}\nTrader result: {trader_result}\n'
                f'Solver result: {solver_result}'
            )

        if cancelled_exc:
            raise cancelled_exc
        return summary


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
            isclose = isclose and math.isclose(aval, bval, rel_tol=Decimal('1e-6'))
        elif isinstance(aval, float):
            isclose = isclose and math.isclose(aval, bval, rel_tol=1e-6)
        else:
            isclose = isclose and aval == bval
    return isclose
