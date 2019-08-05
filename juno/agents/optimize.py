import logging
from decimal import Decimal
from functools import partial
from random import Random
from typing import Optional

from deap import algorithms, base, creator, tools

from juno.agents.summary import TradingSummary
from juno.asyncio import list_async
from juno.components import Informant
from juno.strategies import get_strategy_type
from juno.typing import get_input_type_hints
from juno.utils import flatten

from . import Agent, Backtest

_log = logging.getLogger(__name__)


class Optimize(Agent):
    def __init__(self, informant: Informant, backtest: Backtest):
        super().__init__()
        self._informant = informant
        self._backtest = backtest

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        end: int,
        quote: float,
        strategy: str,
        restart_on_missed_candle: bool = False,
        population_size: int = 50,
        max_generations: int = 1000,
        mutation_probability: Decimal = Decimal('0.2'),
        seed: Optional[int] = None,
    ) -> None:
        # It's useful to set a seed for idempotent results. Useful for debugging.
        # seed = 42  # TODO TEMP
        if seed:
            _log.info(f'seeding randomizer ({seed})')
        random = Random(seed)

        # Objectives:
        #   - max total profit
        #   - min mean drawdown
        #   - min max drawdown
        #   - max mean position profit
        #   - min mean position duration
        weights = (1.0, -1.0, -1.0, 1.0, -1.0)
        # weights = (Decimal(1), Decimal(-1), Decimal(-1), Decimal(1), Decimal(-1))
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

        def result_fitness(result: TradingSummary):
            return map(float, (
                result.profit, result.mean_drawdown, result.max_drawdown,
                result.mean_position_profit, result.mean_position_duration
            ))

        candles = await list_async(
            self._informant.stream_candles(exchange, symbol, interval, start, end))
        fees = self._informant.get_fees(exchange, symbol)
        filters = self._informant.get_filters(exchange, symbol)

        strategy_type = get_strategy_type(strategy)
        keys = list(get_input_type_hints(strategy_type.__init__).keys())  # type: ignore

        agent_config = {
            'exchange': exchange,
            'symbol': symbol,
            'interval': interval,
            'start': start,
            'end': end,
            'quote': quote,
            'restart_on_missed_candle': restart_on_missed_candle,
            'strategy_config': None,  # Need to update before solving problem.
            'candles': candles,
            'fees': fees,
            'filters': filters
        }

        def problem(individual):
            strategy_config = {k: v for k, v in zip(keys, flatten(individual))}
            strategy_config.update({'name': strategy})
            agent_config['strategy_config'] = strategy_config
            return result_fitness(self._backtest.run_sync(**agent_config))

        toolbox = base.Toolbox()
        toolbox.register('evaluate', problem)

        attrs = []
        meta = strategy_type.meta()
        for constraint in meta.values():
            attrs.append(partial(constraint.random, random))

        def strategy_args():
            return (a() for a in attrs)

        toolbox.register('strategy_args', strategy_args)
        toolbox.register(
            'individual', tools.initIterate, creator.Individual, toolbox.strategy_args
        )
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)

        def mut_individual(individual, indpb: float):
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
            cxpb=Decimal('1.0') - toolbox.mutation_probability,
            mutpb=toolbox.mutation_probability,
            stats=None,
            ngen=toolbox.max_generations,
            halloffame=hall,
            verbose=False
        )

        _log.info('done')

        _log.critical(hall[0])
        self.result = list(flatten(hall[0]))

        # TODO: Write test to validate Rust results against Python one to confirm correctness.
