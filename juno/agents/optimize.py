from decimal import Decimal
from typing import List, Optional

from juno import Interval, Timestamp, strategies
from juno.optimization import Optimizer
from juno.trading import MissedCandlePolicy
from juno.utils import get_module_type

from . import Agent


class Optimize(Agent):
    def __init__(self, optimizer: Optimizer) -> None:
        super().__init__()
        self.optimizer = optimizer

    async def run(
        self,
        exchange: str,
        symbols: Optional[List[str]],
        intervals: Optional[List[Interval]],
        start: Timestamp,
        quote: Decimal,
        strategy: str,
        end: Optional[Timestamp] = None,
        missed_candle_policy: Optional[MissedCandlePolicy] = MissedCandlePolicy.IGNORE,
        trailing_stop: Optional[Decimal] = Decimal('0.0'),
        population_size: int = 50,
        max_generations: int = 1000,
        mutation_probability: Decimal = Decimal('0.2'),
        seed: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        strategy_type = get_module_type(strategies, strategy)
        self.result = await self.optimizer.run(
            exchange=exchange,
            symbols=symbols,
            intervals=intervals,
            start=start,
            quote=quote,
            strategy_type=strategy_type,
            end=end,
            missed_candle_policy=missed_candle_policy,
            trailing_stop=trailing_stop,
            population_size=population_size,
            max_generations=max_generations,
            mutation_probability=mutation_probability,
            seed=seed,
            verbose=verbose,
        )

        # TODO: Print best config in pretty format.
