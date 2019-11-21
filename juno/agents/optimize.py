import logging
from decimal import Decimal
from typing import Optional

from juno.components import Chandler, Informant
from juno.optimization import Optimizer, Solver

from . import Agent

_log = logging.getLogger(__name__)


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
            symbol=symbol,
            interval=interval,
            start=start,
            quote=quote,
            strategy=strategy,
            log=_log,
            end=end,
            restart_on_missed_candle=restart_on_missed_candle,
            trailing_stop=trailing_stop,
            population_size=population_size,
            max_generations=max_generations,
            mutation_probability=mutation_probability,
            seed=seed,
            verbose=verbose,
        )
        self.result = optimizer.result
        await optimizer.run()
