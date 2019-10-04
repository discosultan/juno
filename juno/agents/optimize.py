import asyncio
import logging
import math
import sys
from decimal import Decimal
from functools import partial
from random import Random, randrange
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Type

from deap import algorithms, base, creator, tools

from juno.math import floor_multiple
from juno.solvers import Python, Solver
from juno.strategies import Strategy, get_strategy_type
from juno.time import strfinterval, time_ms
from juno.typing import get_input_type_hints
from juno.utils import flatten

from . import Agent

_log = logging.getLogger(__name__)


class Optimize(Agent):
    def __init__(self, solver: Solver, validating_solver: Python) -> None:
        super().__init__()
        self.solver = solver
        self.validating_solver = validating_solver

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
        seed: Optional[int] = None,
    ) -> None:
        now = time_ms()

        if end is None:
            end = floor_multiple(now, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        if seed is None:
            seed = randrange(sys.maxsize)
        _log.info(f'randomizer seed ({seed})')
        random = Random(seed)

        strategy_type = get_strategy_type(strategy)

        # Objectives:
        #   - max profit
        #   - min mean drawdown
        #   - min max drawdown
        #   - max mean position profit
        #   - min mean position duration
        weights = (1.0, -1.0, -1.0, 1.0, -1.0)
        creator.create('FitnessMulti', base.Fitness, weights=weights)
        creator.create('Individual', list, fitness=creator.FitnessMulti)

        toolbox = base.Toolbox()

        # Initialization.
        attrs = [partial(c.random, random) for c in strategy_type.meta.constraints.values()]
        toolbox.register('strategy_args', lambda: (a() for a in attrs))
        toolbox.register(
            'individual', tools.initIterate, creator.Individual, toolbox.strategy_args
        )
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)

        # Operators.

        def mut_individual(individual: list, indpb: float) -> Tuple[list]:
            for i, attr in enumerate(attrs):
                if random.random() < indpb:
                    individual[i] = attr()
            return individual,

        def cx_individual(ind1: list, ind2: list) -> Tuple[list, list]:
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

            ind1[cxpoint1:cxpoint2], ind2[cxpoint1:cxpoint2] = (
                ind2[cxpoint1:cxpoint2], ind1[cxpoint1:cxpoint2]
            )

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

        solve = await self.solver.get(
            strategy_type=strategy_type,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            quote=quote
        )
        toolbox.register('evaluate', lambda ind: solve(*flatten(ind)))

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
            None, lambda: algorithms.eaMuPlusLambda(
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
        )

        _log.info(f'evolution finished in {strfinterval(time_ms() - evolve_start)}')

        best_args = list(flatten(hall[0]))
        best_result = solve(*best_args)
        self.result = OptimizationResult(
            args=_output_as_strategy_args(strategy_type, best_args), result=best_result
        )

        # In case of using other than python solver, run the backtest with final args also with
        # Python solver to assert the equality of results.
        if self.solver != self.validating_solver:
            solver_name = type(self.solver).__name__.lower()
            _log.info(
                f'validating {solver_name} solver result with best args against python solver'
            )
            validation_solve = await self.validating_solver.get(
                strategy_type=strategy_type,
                exchange=exchange,
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
                quote=quote
            )
            validation_result = validation_solve(*best_args)
            if not _isclose(validation_result, best_result):
                raise Exception(
                    f'Optimizer results differ for input {self.result} between python and '
                    f'{solver_name} solvers:\n{validation_result}\n{best_result}'
                )


class OptimizationResult(NamedTuple):
    args: Dict[str, Any]
    result: Dict[str, Any]


def _output_as_strategy_args(strategy_type: Type[Strategy],
                             best_args: List[Any]) -> Dict[str, Any]:
    strategy_config = {'type': strategy_type.__name__.lower()}
    for key, value in zip(get_input_type_hints(strategy_type.__init__).keys(), best_args):
        strategy_config[key] = value
    return strategy_config


def _isclose(a: Tuple[Decimal, ...], b: Tuple[Decimal, ...]) -> bool:
    isclose = True
    for i in range(0, len(a)):
        isclose = isclose and math.isclose(a[i], b[i], rel_tol=Decimal('1e-13'))
    return isclose
