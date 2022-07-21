import logging
from abc import ABC, abstractmethod
from typing import Generic, Literal, Optional, TypeVar, Union

from juno import CandleType, Interval, Timestamp
from juno.brokers import Broker
from juno.primitives.timestamp import Timestamp_
from juno.trading import CloseReason, Position, TradingSummary

TC = TypeVar("TC")
TS = TypeVar("TS")

_log = logging.getLogger(__name__)


class Trader(ABC, Generic[TC, TS]):
    @staticmethod
    @abstractmethod
    def config() -> type[TC]:
        pass

    @staticmethod
    @abstractmethod
    def state() -> type[TS]:
        pass

    @property
    @abstractmethod
    def broker(self) -> Broker:
        pass

    @abstractmethod
    async def initialize(self, config: TC) -> TS:
        pass

    @abstractmethod
    async def run(self, state: TS) -> TradingSummary:
        pass

    @abstractmethod
    async def open_positions(
        self, state: TS, symbols: list[str], short: bool
    ) -> list[Position.Open]:
        pass

    @abstractmethod
    async def close_positions(
        self, state: TS, symbols: list[str], reason: CloseReason
    ) -> list[Position.Closed]:
        pass

    @abstractmethod
    def build_summary(self, state: TS) -> TradingSummary:
        pass

    @staticmethod
    def adjust_start(
        start: Timestamp,
        adjusted_start: Optional[Union[Timestamp, Literal["strategy"]]],
        strategy_maturity: int,
        candle_type: CandleType,
        interval: Interval,
    ) -> Timestamp:
        if adjusted_start == "strategy":
            # Adjust start to accommodate for the required history before a strategy
            # becomes effective. Only do it on first run because subsequent runs mean
            # missed candles and we don't want to fetch passed a missed candle.
            num_historical_candles = strategy_maturity - 1
            if candle_type == "heikin-ashi":
                num_historical_candles += 1
            start = max(start - num_historical_candles * interval, 0)
            _log.info(
                f"fetching {num_historical_candles} candle(s) before start time to warm-up "
                f"strategy; adjusted start set to {Timestamp_.format(start)}"
            )
        elif isinstance(adjusted_start, int):  # Timestamp
            start = Timestamp_.floor(adjusted_start, interval)
            _log.info(f"adjusted start set to {Timestamp_.format(start)}")
        return start
