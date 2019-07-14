from abc import ABC, abstractmethod
from decimal import Decimal

from juno import OrderResult


class Broker(ABC):
    @abstractmethod
    async def buy(self, exchange: str, symbol: str, quote: Decimal, test: bool) -> OrderResult:
        pass

    @abstractmethod
    async def sell(self, exchange: str, symbol: str, base: Decimal, test: bool) -> OrderResult:
        pass
