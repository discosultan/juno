import logging
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, NamedTuple, Optional, get_type_hints

from juno import Interval, MissedCandlePolicy, Timestamp, strategies
from juno.components import Events
from juno.config import format_as_config, get_module_type_constructor
from juno.optimizer import Optimizer, OptimizerConfig, OptimizerState
from juno.storages import Memory, Storage
from juno.traders import BasicConfig
from juno.typing import TypeConstructor, get_input_type_hints
from juno.utils import construct, extract_public

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)


class Optimize(Agent):
    class Config(NamedTuple):
        exchange: str
        symbols: Optional[list[str]]
        intervals: Optional[list[Interval]]
        quote: Decimal
        strategy: dict[str, Any]
        name: Optional[str] = None
        persist: bool = False  # TODO: Not implemented.
        start: Optional[Timestamp] = None
        end: Optional[Timestamp] = None
        missed_candle_policy: Optional[MissedCandlePolicy] = MissedCandlePolicy.IGNORE
        stop_loss: Optional[Decimal] = Decimal('0.0')
        trail_stop_loss: Optional[bool] = True
        take_profit: Optional[Decimal] = Decimal('0.0')
        long: Optional[bool] = True
        short: Optional[bool] = False
        population_size: int = 50
        max_generations: int = 1000
        mutation_probability: Decimal = Decimal('0.2')
        seed: Optional[int] = None
        verbose: bool = False
        fiat_exchange: Optional[str] = None
        fiat_asset: str = 'usdt'

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[OptimizerState] = None

    def __init__(
        self, optimizer: Optimizer, events: Events = Events(), storage: Storage = Memory()
    ) -> None:
        self._optimizer = optimizer
        self._events = events
        self._storage = storage

    async def on_running(self, config: Config, state: State) -> None:
        await super().on_running(config, state)
        if not state.result:
            optimizer_config = construct(
                OptimizerConfig,
                config,
                strategy=get_module_type_constructor(strategies, config.strategy),
            )
            state.result = await self._optimizer.initialize(optimizer_config)
        await self._optimizer.run(state.result)

    async def on_finally(self, config: Config, state: State) -> None:
        assert state
        assert state.result
        assert state.result.summary

        # Create a new typed named tuple for correctly formatting strategy kwargs for the
        # particular strategy type.

        summary = state.result.summary
        cfg = summary.trading_config

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

        trading_config_typings = get_type_hints(BasicConfig)
        trading_config_typings['strategy'] = type_constructor_type
        trading_config_type = NamedTuple('_', trading_config_typings.items())  # type: ignore
        cfg_dict = asdict(cfg)
        cfg_dict['strategy'] = type_constructor_instance
        trading_config_instance = trading_config_type(**cfg_dict)  # type: ignore

        _log.info(f'trading config: {format_as_config(trading_config_instance)}')
        _log.info(f'trading summary: {format_as_config(extract_public(summary.trading_summary))}')
        _log.info(f'portfolio stats: {format_as_config(summary.portfolio_stats)}')
