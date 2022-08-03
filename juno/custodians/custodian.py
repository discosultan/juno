from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from juno import Asset


class Custodian(ABC):
    @abstractmethod
    async def request(self, exchange: str, asset: Asset, amount: Optional[Decimal]) -> Decimal:
        pass

    @abstractmethod
    async def acquire(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        pass

    @abstractmethod
    async def release(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        pass
