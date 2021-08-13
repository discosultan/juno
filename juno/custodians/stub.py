from decimal import Decimal
from typing import Optional

from .custodian import Custodian


class Stub(Custodian):
    async def request_quote(self, exchange: str, asset: str, quote: Optional[Decimal]) -> Decimal:
        if quote is None:
            raise ValueError("Quote must be specified ")
        return quote

    async def acquire(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass

    async def release(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass
