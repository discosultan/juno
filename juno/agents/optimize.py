import logging
from decimal import Decimal
from typing import List, Optional

from juno import Interval, Timestamp, strategies
from juno.optimization import Optimizer
from juno.trading import MissedCandlePolicy
from juno.utils import format_attrs_as_json, get_module_type

from . import Agent

_log = logging.getLogger(__name__)


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

        _log.info(f'trading config: {format_attrs_as_json(self.result.trading_config)}')
        _log.info(f'strategy type: {self.result.strategy_type}')
        _log.info(f'strategy config: {self.result.strategy_config}')
        _log.info(f'trading summary: {format_attrs_as_json(self.result.trading_summary)}')
        _log.info(f'portfolio stats: {format_attrs_as_json(self.result.portfolio_stats)}')
