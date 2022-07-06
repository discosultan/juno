import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Optional

from juno import (
    Interval,
    Interval_,
    Timestamp,
    Timestamp_,
    json,
    serialization,
    stop_loss,
    strategies,
    take_profit,
)
from juno.components import Chandler, Events, Prices
from juno.config import get_module_type_constructor, get_type_name_and_kwargs, kwargs_for
from juno.inspect import construct
from juno.statistics import CoreStatistics, ExtendedStatistics
from juno.storages import Memory, Storage
from juno.traders import Trader
from juno.trading import TradingMode, TradingSummary

from .agent import Agent, AgentStatus

_log = logging.getLogger(__name__)


class Backtest(Agent):
    @dataclass(frozen=True)
    class Config:
        exchange: str
        interval: Interval
        quote: Decimal
        trader: dict[str, Any]
        strategy: dict[str, Any]
        stop_loss: Optional[dict[str, Any]] = None
        take_profit: Optional[dict[str, Any]] = None
        name: Optional[str] = None
        persist: bool = False
        start: Optional[Timestamp] = None
        end: Optional[Timestamp] = None
        fiat_exchange: Optional[str] = None
        fiat_asset: str = "usdt"

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[Any] = None

    def __init__(
        self,
        traders: list[Trader],
        chandler: Chandler,
        prices: Optional[Prices] = None,
        events: Events = Events(),
        storage: Storage = Memory(),
        get_time_ms: Callable[[], int] = Timestamp_.now,
    ) -> None:
        self._traders = {type(t).__name__.lower(): t for t in traders}
        self._chandler = chandler
        self._prices = prices
        self._events = events
        self._storage = storage
        self._get_time_ms = get_time_ms

    async def on_running(self, config: Config, state: State) -> None:
        now = self._get_time_ms()

        assert config.start is None or config.start < now
        assert config.end is None or config.end <= now
        assert config.start is None or config.end is None or config.start < config.end

        start = config.start
        if config.end is None:
            end = now
            _log.info(f"end not specified; end set to {Timestamp_.format(now)}")
        else:
            end = config.end

        trader_name, trader_kwargs = get_type_name_and_kwargs(config.trader)
        trader = self._traders[trader_name]
        trader_config_type = type(trader).config()
        trader_config = construct(
            trader_config_type,
            config,
            **kwargs_for(trader_config_type, trader_kwargs),
            start=start,
            end=end,
            strategy=get_module_type_constructor(strategies, config.strategy),
            stop_loss=(
                None
                if config.stop_loss is None
                else get_module_type_constructor(stop_loss, config.stop_loss)
            ),
            take_profit=(
                None
                if config.take_profit is None
                else get_module_type_constructor(take_profit, config.take_profit)
            ),
            channel=state.name,
            mode=TradingMode.BACKTEST,
        )
        if not state.result:
            state.result = await trader.initialize(trader_config)

        _log.info(
            f"{self.get_name(state)}: running with config "
            f"{json.dumps(serialization.config.serialize(config), indent=4)}"
        )
        await self._events.emit(state.name, "starting", config, state, trader)

        summary = await trader.run(state.result)

        if not self._prices:
            _log.warning("skipping analysis; prices component not available")
            return

        # Fetch necessary market data.
        symbols = [p.symbol for p in summary.positions] + [
            f"btc-{config.fiat_asset}"
        ]  # Use BTC as benchmark.
        fiat_prices = await self._prices.map_asset_prices(
            exchange=config.exchange,
            symbols=symbols,
            start=summary.start,
            end=Timestamp_.ceil(summary.end, Interval_.DAY),
            interval=Interval_.DAY,
            fiat_asset=config.fiat_asset,
            fiat_exchange=config.fiat_exchange,
        )

        _log.info(f"calculating benchmark and portfolio statistics ({config.fiat_asset})")
        stats = ExtendedStatistics.compose(summary=summary, asset_prices=fiat_prices)
        _log.info(json.dumps(serialization.config.serialize(stats), indent=4))

    async def on_finally(self, config: Config, state: State) -> Any:
        summary = self.build_summary(config, state)
        stats = CoreStatistics.compose(summary)
        _log.info(
            f"{self.get_name(state)}: finished with result "
            f"{json.dumps(serialization.config.serialize(stats), indent=4)}"
        )
        await self._events.emit(state.name, "finished", summary)
        return summary

    def build_summary(self, config: Config, state: State) -> TradingSummary:
        assert state.result
        trader_name, _ = get_type_name_and_kwargs(config.trader)
        trader = self._traders[trader_name]
        return trader.build_summary(state.result)
