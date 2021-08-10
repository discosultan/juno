import logging
from decimal import Decimal
from typing import Optional

from juno.components import User

_log = logging.getLogger(__name__)


class Savings:
    def __init__(self, user: User) -> None:
        self._user = user

    async def request_quote(self, exchange: str, asset: str, quote: Optional[Decimal]) -> Decimal:
        if exchange != "binance":
            raise NotImplementedError()

        # TODO: receive from savings account
        return Decimal("0.0")

    async def acquire(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass

    async def release(self, exchange: str, asset: str, quote: Decimal) -> None:
        pass
