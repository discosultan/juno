from decimal import Decimal
from typing import List, Optional

from juno.components import Chandler, Informant
from juno.optimization import Optimizer, Solver

from . import Agent


class Optimize(Agent):
    def __init__(self, solver: Solver, chandler: Chandler, informant: Informant) -> None:
        super().__init__()
        self.solver = solver
        self.chandler = chandler
        self.informant = informant

    async def run(
        self,
        exchange: str,
        symbols: Optional[List[str]],
        intervals: Optional[List[int]],
        start: int,
        quote: Decimal,
        strategy: str,
        end: Optional[int] = None,
        missed_candle_policy: Optional[str] = 'ignore',
        trailing_stop: Optional[Decimal] = Decimal('0.0'),
        population_size: int = 50,
        max_generations: int = 1000,
        mutation_probability: Decimal = Decimal('0.2'),
        seed: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        optimizer = Optimizer(
            solver=self.solver,
            chandler=self.chandler,
            informant=self.informant,
            exchange=exchange,
            symbols=symbols,
            intervals=intervals,
            start=start,
            quote=quote,
            strategy=strategy,
            end=end,
            missed_candle_policy=missed_candle_policy,
            trailing_stop=trailing_stop,
            population_size=population_size,
            max_generations=max_generations,
            mutation_probability=mutation_probability,
            seed=seed,
            verbose=verbose,
        )
        await optimizer.run()
        self.result = optimizer.result
