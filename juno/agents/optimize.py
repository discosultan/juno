import logging
from decimal import Decimal
from typing import List, NamedTuple, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Event
from juno.modules import get_module_type
from juno.optimization import OptimizationSummary, Optimizer
from juno.storages import Memory, Storage
from juno.trading import MissedCandlePolicy
from juno.typing import get_input_type_hints
from juno.utils import format_as_config

from .agent import Agent

_log = logging.getLogger(__name__)


class Optimize(Agent):
    class Config(NamedTuple):
        exchange: str
        symbols: Optional[List[str]]
        intervals: Optional[List[Interval]]
        start: Timestamp
        quote: Decimal
        strategy: str
        name: Optional[str] = None
        persist: bool = False
        end: Optional[Timestamp] = None
        missed_candle_policy: Optional[MissedCandlePolicy] = MissedCandlePolicy.IGNORE
        trailing_stop: Optional[Decimal] = Decimal('0.0')
        long: Optional[bool] = True
        short: Optional[bool] = False
        population_size: int = 50
        max_generations: int = 1000
        mutation_probability: Decimal = Decimal('0.2')
        seed: Optional[int] = None
        verbose: bool = False

    def __init__(
        self, optimizer: Optimizer, event: Event = Event(), storage: Storage = Memory()
    ) -> None:
        self._optimizer = optimizer
        self._event = event
        self._storage = storage

    async def on_running(self, config: Config, state: Agent.State[OptimizationSummary]) -> None:
        await super().on_running(config, state)
        state.result = OptimizationSummary()
        await self._optimizer.run(
            exchange=config.exchange,
            symbols=config.symbols,
            intervals=config.intervals,
            start=config.start,
            quote=config.quote,
            strategy=config.strategy,
            end=config.end,
            missed_candle_policy=config.missed_candle_policy,
            trailing_stop=config.trailing_stop,
            long=config.long,
            short=config.short,
            population_size=config.population_size,
            max_generations=config.max_generations,
            mutation_probability=config.mutation_probability,
            seed=config.seed,
            verbose=config.verbose,
            summary=state.result,
        )

    async def on_finally(self, config: Config, state: Agent.State[OptimizationSummary]) -> None:
        for ind in state.result.best:
            # Create a new typed named tuple for correctly formatting strategy kwargs for the
            # particular strategy type.

            trading_config = ind.trading_config
            strategy = trading_config.strategy
            strategy_kwargs = trading_config.strategy_kwargs
            strategy_type = get_module_type(strategies, strategy)

            strategy_kwargs_typings = get_input_type_hints(strategy_type.__init__)  # type: ignore
            strategy_kwargs_type = NamedTuple('_', strategy_kwargs_typings.items())  # type: ignore
            strategy_kwargs_instance = strategy_kwargs_type(*strategy_kwargs.values())

            trading_config_typings = get_input_type_hints(trading_config)
            trading_config_typings['strategy_kwargs'] = strategy_kwargs_type
            trading_config_type = NamedTuple('_', trading_config_typings.items())  # type: ignore
            x = ind.trading_config._asdict()
            x['strategy_kwargs'] = strategy_kwargs_instance
            trading_config_instance = trading_config_type(*x.values())

            _log.info(f'trading config: {format_as_config(trading_config_instance)}')
            _log.info(f'trading summary: {format_as_config(ind.trading_summary)}')
            _log.info(f'portfolio stats: {format_as_config(ind.portfolio_stats)}')

    def _get_result_type(self, config: Config) -> type:
        return OptimizationSummary
