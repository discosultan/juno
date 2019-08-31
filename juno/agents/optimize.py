import logging
import math
from decimal import Decimal
from functools import partial
from random import Random
from typing import Optional

from deap import algorithms, base, creator, tools

from juno.asyncio import list_async
from juno.components import Informant
from juno.math import floor_multiple
from juno.solvers import Python, get_solver_type
from juno.strategies import get_strategy_type
from juno.time import time_ms
from juno.typing import get_input_type_hints
from juno.utils import flatten

from . import Agent

_log = logging.getLogger(__name__)


class Optimize(Agent):
    def __init__(self, informant: Informant):
        super().__init__()
        self._informant = informant

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        quote: Decimal,
        strategy: str,
        end: Optional[int] = None,
        restart_on_missed_candle: bool = False,
        population_size: int = 50,
        max_generations: int = 1000,
        mutation_probability: Decimal = Decimal('0.2'),
        solver: str = 'rust',
        seed: Optional[int] = None,
    ) -> None:
        now = time_ms()

        if end is None:
            end = floor_multiple(now, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        # It's useful to set a seed for idempotent results. Helpful for debugging.
        if seed is not None:
            _log.info(f'seeding randomizer ({seed})')
        random = Random(seed)

        # Objectives:
        #   - max total profit
        #   - min mean drawdown
        #   - min max drawdown
        #   - max mean position profit
        #   - min mean position duration
        weights = (1.0, -1.0, -1.0, 1.0, -1.0)
        # weights = (Decimal(1), Decimal(-1), Decimal (-1), Decimal(1), Decimal(-1))
        # weights = (1.0, -0.5, -1.0, 1.0, -0.5)
        # weights = (1.0, -0.1, -1.0, 0.1, -0.1)
        creator.create('FitnessMulti', base.Fitness, weights=weights)
        creator.create('Individual', list, fitness=creator.FitnessMulti)

        # def attr_period() -> int:
        #     return random.randint(1, 100)

        # def attr_neg_pos_thresholds() -> Tuple[float, float]:
        #     down_threshold = random.uniform(-2.0, -0.1)
        #     up_threshold = random.uniform(0.1, 2.0)
        #     return down_threshold, up_threshold

        # def attr_down_up_thresholds() -> Tuple[float, float]:
        #     down_threshold = random.uniform(0.1, 0.4)
        #     up_threshold = random.uniform(0.6, 0.9)
        #     return down_threshold, up_threshold

        # def attr_rsi_down_threshold() -> float:
        #     return random.uniform(10.0, 40.0)

        # def attr_rsi_up_threshold() -> float:
        #     return random.uniform(60.0, 90.0)

        candles = await list_async(
            self._informant.stream_candles(exchange, symbol, interval, start, end)
        )
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)

        strategy_type = get_strategy_type(strategy)

        solver_instance = get_solver_type(solver)(
            candles=candles,
            fees=fees,
            filters=filters,
            strategy_type=strategy_type,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            quote=quote
        )
        await solver_instance.__aenter__()

        toolbox = base.Toolbox()
        toolbox.register('evaluate', lambda ind: solver_instance.solve(*flatten(ind)))

        attrs = [partial(c.random, random) for c in strategy_type.meta().values()]
        toolbox.register('strategy_args', lambda: (a() for a in attrs))
        toolbox.register(
            'individual', tools.initIterate, creator.Individual, toolbox.strategy_args
        )
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)

        def mut_individual(individual, indpb: float) -> tuple:
            for i, attr in enumerate(attrs):
                if random.random() < indpb:
                    individual[i] = attr()
            return individual,

        def cx_individual(ind1, ind2):
            end = len(ind1) - 1

            # Variant A.
            cxpoint1, cxpoint2 = 0, -1
            while cxpoint2 < cxpoint1:
                cxpoint1 = random.randint(0, end)
                cxpoint2 = random.randint(0, end)

            # Variant B.
            # cxpoint1 = random.randint(0, end)
            # cxpoint2 = random.randint(cxpoint1, end)

            cxpoint2 += 1

            ind1[cxpoint1:cxpoint2], ind2[cxpoint1:cxpoint2] = ind2[cxpoint1:cxpoint2
                                                                    ], ind1[cxpoint1:cxpoint2]

            return ind1, ind2

        # eta - Crowding degree of the crossover. A high eta will produce children resembling to
        # their parents, while a small eta will produce solutions much more different.

        # toolbox.register('mate', tools.tools.cxSimulatedBinaryBounded, low=BOUND_LOW,
        #                  up=BOUND_UP, eta=20.0)
        toolbox.register('mate', cx_individual)
        # toolbox.register('mutate', tools.mutPolynomialBounded, low=BOUND_LOW, up=BOUND_UP,
        #                  eta=20.0, indpb=1.0 / NDIM)
        toolbox.register('mutate', mut_individual, indpb=1.0 / len(attrs))
        toolbox.register('select', tools.selNSGA2)

        toolbox.population_size = population_size
        toolbox.max_generations = max_generations
        toolbox.mutation_probability = mutation_probability

        _log.info('evolving')

        pop = toolbox.population(n=toolbox.population_size)
        pop = toolbox.select(pop, len(pop))

        hall = tools.HallOfFame(1)

        # Returns the final population and logbook with the statistics of the evolution.
        final_pop, stat = algorithms.eaMuPlusLambda(
            pop,
            toolbox,
            mu=toolbox.population_size,
            lambda_=toolbox.population_size,
            cxpb=Decimal(1) - toolbox.mutation_probability,
            mutpb=toolbox.mutation_probability,
            stats=None,
            ngen=toolbox.max_generations,
            halloffame=hall,
            verbose=False
        )

        best_args = list(flatten(hall[0]))
        _log.info(f'final backtest result: {solver_instance.solve(*best_args)}')
        self.result = _output_as_strategy_args(strategy_type, best_args)

        # In case of using other than python solver, run the backtest with final args also with
        # Python solver to assert the equality of results.
        if solver != 'python':
            _log.info(f'validating {solver} solver result with best args against python solver')
            python_solver = Python(
                candles, fees, filters, strategy_type, symbol, interval, start, end, quote
            )
            await python_solver.__aenter__()

            python_result = python_solver.solve(*best_args)
            native_result = solver_instance.solve(*best_args)
            if not _isclose(native_result, python_result):
                raise Exception(
                    f'Optimizer results differ for input {self.result} between '
                    f'Python and {solver.capitalize()} '
                    f'solvers:\n{python_result}\n{native_result}'
                )


def _output_as_strategy_args(strategy_type, best_args):
    strategy_config = {'name': strategy_type.__name__.lower()}
    for key, value in zip(get_input_type_hints(strategy_type.__init__).keys(), best_args):
        strategy_config[key] = value
    return strategy_config


def _isclose(a, b):
    isclose = True
    for i in range(0, len(a)):
        isclose = isclose and math.isclose(a[i], b[i], rel_tol=Decimal('1e-14'))
    return isclose
