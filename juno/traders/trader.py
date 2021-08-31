from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from juno.brokers import Broker
from juno.trading import CloseReason, Position, TradingSummary

TC = TypeVar("TC")
TS = TypeVar("TS")


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
