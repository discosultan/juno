import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Generic, Optional, TypeVar

from juno.brokers import Broker
from juno.components import User
from juno.trading import CloseReason, Position, TradingMode, TradingSummary

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

    @property
    @abstractmethod
    def user(self) -> User:
        pass

    @abstractmethod
    async def initialize(self, config: TC) -> TS:
        pass

    @abstractmethod
    async def run(self, state: TS) -> TradingSummary:
        pass

    @abstractmethod
    async def open_positions(self, state: TS, symbols: list[str]) -> list[Position.Open]:
        pass

    @abstractmethod
    async def close_positions(
        self, state: TS, symbols: list[str], reason: CloseReason
    ) -> list[Position.Closed]:
        pass

    async def request_quote(
        self, quote: Optional[Decimal], exchange: str, asset: str, mode: TradingMode
    ) -> Decimal:
        if mode in [TradingMode.BACKTEST, TradingMode.PAPER]:
            if quote is None:
                raise ValueError("Quote must be specified when backtesting or paper trading")
            return quote

        available_quote = (
            await self.user.get_balance(exchange=exchange, account="spot", asset=asset)
        ).available

        if quote is None:
            _log.info(f"quote not specified; using available {available_quote} {asset}")
            return available_quote

        if available_quote < quote:
            raise ValueError(
                f"Requesting trading with {quote} {asset} but only {available_quote} available"
            )

        return quote
