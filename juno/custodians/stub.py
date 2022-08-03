from decimal import Decimal
from typing import Optional

from juno import Asset

from .custodian import Custodian


class Stub(Custodian):
    async def request(self, exchange: str, asset: Asset, amount: Optional[Decimal]) -> Decimal:
        if amount is None:
            raise ValueError("Amount must be specified ")
        return amount

    async def acquire(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        pass

    async def release(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        pass
