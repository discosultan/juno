from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from juno import OrderResult


class Broker(ABC):
    # TODO: Support order types. In some cases we want to fill as much possible; in other cases
    # we want to fail of not enough available on orderbook, for example.
    @abstractmethod
    async def buy(
        self,
        exchange: str,
        account: str,
        symbol: str,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
    ) -> OrderResult:
        pass

    @abstractmethod
    async def sell(
        self,
        exchange: str,
        account: str,
        symbol: str,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
    ) -> OrderResult:
        pass

    @staticmethod
    def validate_funds(size: Optional[Decimal], quote: Optional[Decimal]) -> None:
        if not size and not quote:
            raise ValueError('Either size or quote must be specified')
        if size and quote:
            raise ValueError('Size and quote cannot be both specified')
