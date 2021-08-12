import logging
from decimal import Decimal
from typing import Optional

from juno.components import User

from .custodian import Custodian

_log = logging.getLogger(__name__)


class Spot(Custodian):
    def __init__(self, user: User) -> None:
        self._user = user

    async def request_quote(self, exchange: str, asset: str, quote: Optional[Decimal]) -> Decimal:
        available_quote = (
            await self._user.get_balance(exchange=exchange, account="spot", asset=asset)
        ).available

        if quote is None:
            _log.info(f"quote not specified; using available {available_quote} {asset}")
            return available_quote

        if available_quote < quote:
            raise ValueError(
                f"Requesting trading with {quote} {asset} but only {available_quote} available"
            )

        return quote

    async def acquire(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass

    async def release(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass
