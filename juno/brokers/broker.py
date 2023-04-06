from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from juno import Account, OrderResult, Symbol


class Broker(ABC):
    # TODO: Support order types. In some cases we want to fill as much as possible; in other cases
    # we want to fail if not enough available on orderbook, for example.
    @abstractmethod
    async def buy(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
        ensure_size: bool = False,  # Only if buying by size.
        leverage: Optional[str] = None,
    ) -> OrderResult:
        pass

    @abstractmethod
    async def sell(
        self,
        exchange: str,
        account: Account,
        symbol: Symbol,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        test: bool = True,
        leverage: Optional[str] = None,
    ) -> OrderResult:
        pass

    @staticmethod
    def validate_funds(size: Optional[Decimal], quote: Optional[Decimal]) -> None:
        if size is None and quote is None:
            raise ValueError("Either size or quote must be specified")
        if size is not None and quote is not None:
            raise ValueError("Size and quote cannot be both specified")
        if size is not None and size == 0:
            raise ValueError("Size specified but zero")
        if quote is not None and quote == 0:
            raise ValueError("Quote specified but zero")
