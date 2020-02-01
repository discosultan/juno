import asyncio
import logging
import math
import sys
from decimal import Decimal
from functools import partial
from itertools import product
from random import Random, randrange
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Type

from deap import algorithms, base, creator, tools

from juno import Candle, InsufficientBalance, Interval, Timestamp, strategies
from juno.components import Chandler, Informant
from juno.math import Choice, Constant, Constraint, ConstraintChoice, Uniform, floor_multiple
from juno.strategies import Strategy
from juno.time import DAY_MS, strfinterval, strfspan, time_ms
from juno.trading import (
    MissedCandlePolicy, Trader, get_benchmark_statistics, get_portfolio_statistics
)
from juno.typing import get_input_type_hints
from juno.utils import flatten, format_attrs_as_json, get_module_type

from .deap import cx_uniform, mut_individual
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


class Optimizer:
    def __init__(
        self,
        solver: Solver,
        chandler: Chandler,
        informant: Informant,
        exchange: str,
        start: Timestamp,
        quote: Decimal,
        strategy: str,
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
    ) -> None:
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

        _log.info(f'randomizer seed ({seed})')

        self.solver = solver
        self.chandler = chandler
        self.informant = informant
        self.exchange = exchange
        self.symbols = symbols
        self.intervals = intervals
        self.start = start
        self.quote = quote
        self.strategy = strategy
        self.end = end
        self.missed_candle_policy = missed_candle_policy
        self.trailing_stop = trailing_stop
        self.population_size = population_size
        self.max_generations = max_generations
        self.mutation_probability = mutation_probability
        self.seed = seed
        self.verbose = verbose

        self.result = OptimizationResult()

    async def run(self) -> None:
        symbols = self.informant.list_symbols(self.exchange, self.symbols)
        intervals = self.informant.list_candle_intervals(self.exchange, self.intervals)

        # TODO: How to resolve best exchange / symbol for FIAT statistical analysis.
        # btc_fiat_symbol = 'btc-eur'
        # btc_fiat_exchange = 'coinbase'
        # btc_fiat_exchanges = self.informant.list_exchanges_supporting_symbol(btc_fiat_symbol)
        # if len(btc_fiat_exchanges) == 0:
        #     _log.warning(f'no exchange with fiat symbol {btc_fiat_symbol} found; skipping '
        #                  'calculating further statistics')
        #     return
        # btc_fiat_exchange = btc_fiat_exchanges[0]

        candles: Dict[Tuple[str, int, bool], List[Candle]] = {}
        # Fetch candles specific to statistical analysis.
        await asyncio.gather(
            # Binance also supports FIAT symbols but has limited candle data, hence Coinbase.
            self._fetch_candles(candles, 'coinbase', 'btc-eur', DAY_MS,
                                fill_missing_with_last=True),
            *(self._fetch_candles(candles, self.exchange, s, DAY_MS, fill_missing_with_last=True)
              for s in symbols)
        )
        # Fetch candles for backtesting.
        await asyncio.gather(
            *(self._fetch_candles(candles, self.exchange, s, i, fill_missing_with_last=False)
              for s, i in product(symbols, intervals))
        )

        for (s, i, _f), _v in ((k, v) for k, v in candles.items() if len(v) == 0):
            # TODO: Exclude from optimization.
            _log.warning(f'no {s} {strfinterval(i)} candles found between '
                         f'{strfspan(self.start, self.end)}')

        fees_filters = {s: self.informant.get_fees_filters(self.exchange, s) for s in symbols}

        # Prepare benchmark stats.
        benchmark_stats = get_benchmark_statistics(candles[('btc-eur', DAY_MS, True)])

        # NB! All the built-in algorithms in DEAP use random module directly. This doesn't work for
        # us because we want to be able to use multiple optimizers with different random seeds.
        # Therefore we need to use custom algorithms to support passing in our own `random.Random`.
        random = Random(self.seed)

        strategy_type = get_module_type(strategies, self.strategy)

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
            _build_attr(self.missed_candle_policy, _missed_candle_policy_constraint, random),
            _build_attr(self.trailing_stop, _trailing_stop_constraint, random),
            *(partial(c.random, random) for c in strategy_type.meta.constraints.values())
        ]
        toolbox.register('strategy_args', lambda: (a() for a in attrs))
        toolbox.register(
            'individual', tools.initIterate, creator.Individual, toolbox.strategy_args
        )
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)

        # Operators.

        indpb = 1.0 / len(attrs)

        # eta - Crowding degree of the crossover. A high eta will produce children resembling to
        # their parents, while a small eta will produce solutions much more different.

        # toolbox.register('mate', tools.tools.cxSimulatedBinaryBounded, low=BOUND_LOW,
        #                  up=BOUND_UP, eta=20.0)
        toolbox.register('mate', cx_uniform(random), indpb=indpb)
        # toolbox.register('mutate', tools.mutPolynomialBounded, low=BOUND_LOW, up=BOUND_UP,
        #                  eta=20.0, indpb=1.0 / NDIM)
        toolbox.register('mutate', mut_individual(random), attrs=attrs, indpb=indpb)
        toolbox.register('select', tools.selNSGA2)

        def evaluate(ind: List[Any]) -> SolverResult:
            return self.solver.solve(
                candles[('btc-eur', DAY_MS, True)],
                candles[(ind[0], DAY_MS, True)],
                benchmark_stats,
                strategy_type,
                self.quote,
                candles[(ind[0], ind[1], False)],
                *fees_filters[ind[0]],
                *flatten(ind)
            )

        toolbox.register('evaluate', evaluate)

        toolbox.population_size = self.population_size
        toolbox.max_generations = self.max_generations
        toolbox.mutation_probability = self.mutation_probability

        pop = toolbox.population(n=toolbox.population_size)
        pop = toolbox.select(pop, len(pop))

        hall = tools.HallOfFame(1)

        _log.info('evolving')
        evolve_start = time_ms()

        # Returns the final population and logbook with the statistics of the evolution.
        final_pop, stat = await asyncio.get_running_loop().run_in_executor(
            None, partial(
                algorithms.eaMuPlusLambda,
                pop,
                toolbox,
                mu=toolbox.population_size,
                lambda_=toolbox.population_size,
                cxpb=Decimal('1.0') - toolbox.mutation_probability,
                mutpb=toolbox.mutation_probability,
                stats=None,
                ngen=toolbox.max_generations,
                halloffame=hall,
                verbose=self.verbose,
            )
        )

        _log.info(f'evolution finished in {strfinterval(time_ms() - evolve_start)}')

        best_args = list(flatten(hall[0]))
        best_result = self.solver.solve(
            candles[('btc-eur', DAY_MS, True)],
            candles[(best_args[0], DAY_MS, True)],
            benchmark_stats,
            strategy_type,
            self.quote,
            candles[(best_args[0], best_args[1], False)],
            *fees_filters[best_args[0]],
            *best_args
        )
        self.result = OptimizationResult(
            symbol=best_args[0],
            interval=best_args[1],
            missed_candle_policy=best_args[2],
            trailing_stop=best_args[3],
            strategy_config=_output_as_strategy_config(strategy_type, best_args[4:]),
            result=best_result,
        )

        # Validate our results by running a backtest in actual trader to ensure correctness.
        solver_name = type(self.solver).__name__.lower()
        _log.info(
            f'validating {solver_name} solver result with best args against actual trader'
        )
        trader = Trader(
            chandler=self.chandler,
            informant=self.informant,
            exchange=self.exchange,
            symbol=self.result.symbol,
            interval=self.result.interval,
            start=floor_multiple(self.start, self.result.interval),
            end=floor_multiple(self.end, self.result.interval),
            quote=self.quote,
            new_strategy=lambda: strategy_type(**self.result.strategy_config),
            missed_candle_policy=self.result.missed_candle_policy,
            trailing_stop=self.result.trailing_stop,
            adjust_start=False,
        )
        try:
            await trader.run()
        except InsufficientBalance:
            pass
        validation_result = SolverResult.from_trading_summary(
            trader.summary,
            get_portfolio_statistics(
                benchmark_stats,
                candles[('btc-eur', DAY_MS, True)],
                {self.result.symbol: candles[(self.result.symbol, DAY_MS, True)]},
                trader.summary
            )
        )
        if not _isclose(validation_result, best_result):
            raise Exception(
                f'Optimizer results differ for input {self.result} between trader and '
                f'{solver_name} solver:\n{format_attrs_as_json(validation_result)}'
                f'\n{format_attrs_as_json(best_result)}'
            )
        _log.info(f'Trading summary: {format_attrs_as_json(trader.summary)}')

    async def _fetch_candles(
        self,
        candles: Dict[Tuple[str, int, bool], List[Candle]],
        exchange: str,
        symbol: str,
        interval: int,
        fill_missing_with_last: bool
    ) -> None:
        candles[(symbol, interval, fill_missing_with_last)] = await self.chandler.list_candles(
            exchange, symbol, interval, floor_multiple(self.start, interval),
            floor_multiple(self.end, interval), fill_missing_with_last=fill_missing_with_last
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


class OptimizationResult(NamedTuple):
    symbol: str = ''
    interval: Interval = 0
    missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
    trailing_stop: Decimal = Decimal('0.0')
    strategy_config: Dict[str, Any] = {}
    result: SolverResult = SolverResult()


def _output_as_strategy_config(strategy_type: Type[Strategy],
                               strategy_args: List[Any]) -> Dict[str, Any]:
    strategy_config = {}
    for key, value in zip(get_input_type_hints(strategy_type.__init__).keys(), strategy_args):
        strategy_config[key] = value
    return strategy_config


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
