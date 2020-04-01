from abc import ABC, abstractmethod
from decimal import Decimal

from juno import OrderResult


class Broker(ABC):
    # TODO: Support order types. In some cases we want to fill as much possible; in other cases
    # we want to fail of not enough available on orderbook, for example.
    @abstractmethod
    async def buy(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        pass

    @abstractmethod
    async def buy_by_quote(
        self, exchange: str, symbol: str, quote: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        pass

    @abstractmethod
    async def sell(
        self, exchange: str, symbol: str, size: Decimal, test: bool, margin: bool = False
    ) -> OrderResult:
        pass
