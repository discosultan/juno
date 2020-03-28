from abc import ABC, abstractmethod
from decimal import Decimal

from juno import OrderResult


class Broker(ABC):
    @abstractmethod
    async def buy(
        self,
        exchange: str,
        symbol: str,
        base: Decimal = Decimal('0.0'),
        quote: Decimal = Decimal('0.0'),
        test: bool = True,
    ) -> OrderResult:
        pass

    @abstractmethod
    async def sell(self, exchange: str, symbol: str, base: Decimal, test: bool) -> OrderResult:
        pass
