import asyncio
import logging
import math
import random
import sys
from decimal import Decimal
from functools import partial
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Type

from deap import algorithms, base, creator, tools

import juno.json as json
from juno import InsufficientBalance
from juno.components import Chandler, Informant
from juno.logging import disabled_log
from juno.math import Choice, Constant, Uniform, floor_multiple
from juno.solvers import Solver, SolverResult
from juno.strategies import Strategy, get_strategy_type, new_strategy
from juno.time import strfinterval, time_ms
from juno.trading import TradingLoop
from juno.typing import get_input_type_hints
from juno.utils import flatten

from . import Agent

_log = logging.getLogger(__name__)

_restart_on_missed_candle_constraint = Choice([True, False])
_trailing_stop_constraint = Choice([
    Constant(Decimal(0)),
    Uniform(Decimal('0.0001'), Decimal('0.9999')),
])


class Optimize(Agent):
    def __init__(self, solver: Solver, chandler: Chandler, informant: Informant) -> None:
        super().__init__()
        self.solver = solver
        self.chandler = chandler
        self.informant = informant

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        quote: Decimal,
        strategy: str,
        end: Optional[int] = None,
        restart_on_missed_candle: Optional[bool] = False,
        trailing_stop: Optional[Decimal] = Decimal(0),
        population_size: int = 50,
        max_generations: int = 1000,
        mutation_probability: Decimal = Decimal('0.2'),
        seed: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        now = time_ms()

        if end is None:
            end = floor_multiple(now, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        if seed is None:
            seed = random.randrange(sys.maxsize)
        _log.info(f'randomizer seed ({seed})')
        # NB! We cannot initialize a new randomizer here if we keep using DEAP's internal
        # algorithms for mutation, crossover, selection. These algos are using the random module
        # directly and we have not way to pass our randomizer in. Hence we seend the random
        # module directly.
        # random = Random(seed)  # <-- Don't do this!
        random.seed(seed)

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
        attrs = [
            ((lambda: _restart_on_missed_candle_constraint.random(random))  # type: ignore
             if restart_on_missed_candle is None else (lambda: restart_on_missed_candle)),
            ((lambda: _trailing_stop_constraint.random(random).random(random))  # type: ignore
             if trailing_stop is None else (lambda: trailing_stop)  # type: ignore
             )
        ] + [partial(c.random, random) for c in strategy_type.meta.constraints.values()]
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
            quote=quote,
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
                verbose=verbose,
            )
        )

        _log.info(f'evolution finished in {strfinterval(time_ms() - evolve_start)}')

        best_args = list(flatten(hall[0]))
        best_result = solve(*best_args)
        self.result = OptimizationResult(
            restart_on_missed_candle=best_args[0],
            trailing_stop=best_args[1],
            strategy_config=_output_as_strategy_config(strategy_type, best_args[2:]),
            result=best_result,
        )

        # Validate our results by running a backtest in actual trading loop to ensure correctness.
        solver_name = type(self.solver).__name__.lower()
        _log.info(
            f'validating {solver_name} solver result with best args against actual trading loop'
        )
        loop = TradingLoop(
            chandler=self.chandler,
            informant=self.informant,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            quote=quote,
            new_strategy=lambda: new_strategy(self.result.strategy_config),
            log=disabled_log,
            restart_on_missed_candle=self.result.restart_on_missed_candle,
            trailing_stop=self.result.trailing_stop,
            adjust_start=False,
        )
        try:
            await loop.run()
        except InsufficientBalance:
            pass
        validation_result = SolverResult.from_trading_summary(loop.summary)
        if not _isclose(validation_result, best_result):
            raise Exception(
                f'Optimizer results differ for input {self.result} between trading loop and '
                f'{solver_name} solver:\n{validation_result}\n{best_result}'
            )

        _log.info(json.dumps(self.result, indent=4))


class OptimizationResult(NamedTuple):
    restart_on_missed_candle: bool
    trailing_stop: Decimal
    strategy_config: Dict[str, Any]
    result: Dict[str, Any]


def _output_as_strategy_config(strategy_type: Type[Strategy],
                               strategy_args: List[Any]) -> Dict[str, Any]:
    strategy_config = {'type': strategy_type.__name__.lower()}
    for key, value in zip(get_input_type_hints(strategy_type.__init__).keys(), strategy_args):
        strategy_config[key] = value
    return strategy_config


def _isclose(a: Tuple[Any, ...], b: Tuple[Any, ...]) -> bool:
    isclose = True
    for aval, bval in zip(a, b):
        if isinstance(aval, Decimal):
            isclose = isclose and math.isclose(aval, bval, rel_tol=Decimal('1e-13'))
        elif isinstance(aval, float):
            isclose = isclose and math.isclose(aval, bval, rel_tol=1e-13)
        else:
            isclose = isclose and aval == bval
    return isclose
