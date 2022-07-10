from decimal import Decimal
from typing import Optional

from juno import Asset

from .custodian import Custodian


class Stub(Custodian):
    async def request_quote(
        self, exchange: str, asset: Asset, quote: Optional[Decimal]
    ) -> Decimal:
        if quote is None:
            raise ValueError("Quote must be specified ")
        return quote

    async def acquire(self, exchange: str, asset: Asset, quote: Decimal) -> None:
        pass

    async def release(self, exchange: str, asset: Asset, quote: Decimal) -> None:
        pass
