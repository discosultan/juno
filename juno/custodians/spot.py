import logging
from decimal import Decimal
from typing import Optional

from juno import Asset
from juno.components import User

from .custodian import Custodian

_log = logging.getLogger(__name__)


class Spot(Custodian):
    def __init__(self, user: User) -> None:
        self._user = user

    async def request(self, exchange: str, asset: Asset, amount: Optional[Decimal]) -> Decimal:
        available_amount = (
            await self._user.get_balance(exchange=exchange, account="spot", asset=asset)
        ).available

        if amount is None:
            _log.info(f"amount not specified; using available {available_amount} {asset}")
            return available_amount

        if available_amount < amount:
            raise ValueError(
                f"Requesting trading with {amount} {asset} but only {available_amount} available"
            )

        return amount

    async def acquire(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        pass

    async def release(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        pass
