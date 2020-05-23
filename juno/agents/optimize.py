import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import List, NamedTuple, Optional, get_type_hints

from juno import Interval, MissedCandlePolicy, Timestamp
from juno.components import Events
from juno.optimization import OptimizationSummary, Optimizer
from juno.storages import Memory, Storage
from juno.traders import Basic
from juno.typing import TypeConstructor, get_input_type_hints
from juno.utils import format_as_config

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)


class Optimize(Agent):
    class Config(NamedTuple):
        exchange: str
        symbols: Optional[List[str]]
        intervals: Optional[List[Interval]]
        quote: Decimal
        strategy: str
        name: Optional[str] = None
        persist: bool = False
        start: Optional[Timestamp] = None
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

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[OptimizationSummary] = None

    def __init__(
        self, optimizer: Optimizer, events: Events = Events(), storage: Storage = Memory()
    ) -> None:
        self._optimizer = optimizer
        self._events = events
        self._storage = storage

    async def on_running(self, config: Config, state: State) -> None:
        await super().on_running(config, state)
        if not state.result:
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

    async def on_finally(self, config: Config, state: State) -> None:
        assert state.result
        for ind in state.result.best:
            # Create a new typed named tuple for correctly formatting strategy kwargs for the
            # particular strategy type.

            cfg = ind.trading_config

            strategy_kwargs_typings = get_input_type_hints(cfg.strategy.type_.__init__)
            strategy_kwargs_type = NamedTuple('_', strategy_kwargs_typings.items())  # type: ignore
            strategy_kwargs_instance = strategy_kwargs_type(*cfg.strategy.kwargs.values())

            type_constructor_typings = get_type_hints(TypeConstructor)
            type_constructor_typings['kwargs'] = strategy_kwargs_type
            type_constructor_type = NamedTuple(  # type: ignore
                '_', type_constructor_typings.items()
            )
            type_constructor_instance = type_constructor_type(  # type: ignore
                name=cfg.strategy.name,
                args=cfg.strategy.args,
                kwargs=strategy_kwargs_instance,
            )

            trading_config_typings = get_type_hints(Basic.Config)
            trading_config_typings['strategy'] = type_constructor_type
            trading_config_type = NamedTuple('_', trading_config_typings.items())  # type: ignore
            cfg_dict = cfg._asdict()
            cfg_dict['strategy'] = type_constructor_instance
            trading_config_instance = trading_config_type(**cfg_dict)  # type: ignore

            _log.info(f'trading config: {format_as_config(trading_config_instance)}')
            _log.info(f'trading summary: {format_as_config(ind.trading_summary)}')
            _log.info(f'portfolio stats: {format_as_config(ind.portfolio_stats)}')
