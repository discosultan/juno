from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional


class Custodian(ABC):
    @abstractmethod
    async def request_quote(self, exchange: str, asset: str, quote: Optional[Decimal]) -> Decimal:
        pass

    @abstractmethod
    async def acquire(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass

    @abstractmethod
    async def release(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass
