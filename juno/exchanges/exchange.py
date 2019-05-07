from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, AsyncIterable, Dict, Optional, Tuple

from juno import Balance, Candle, Fees, OrderResult, OrderType, Side, SymbolInfo, TimeInForce


class Exchange(ABC):

    @abstractmethod
    async def map_fees(self) -> Dict[str, Fees]:
        pass

    @abstractmethod
    async def map_symbol_infos(self) -> Dict[str, SymbolInfo]:
        pass

    @abstractmethod
    async def stream_balances(self) -> AsyncIterable[Dict[str, Balance]]:
        yield  # type: ignore

    @abstractmethod
    async def stream_candles(self, symbol: str, interval: int, start: int, end: int
                             ) -> AsyncIterable[Tuple[Candle, bool]]:
        yield  # type: ignore

    @abstractmethod
    async def stream_depth(self, symbol: str) -> AsyncIterable[Any]:
        yield

    @abstractmethod
    async def stream_orders(self) -> AsyncIterable[Any]:
        yield

    @abstractmethod
    async def place_order(
            self,
            symbol: str,
            side: Side,
            type_: OrderType,
            size: Decimal,
            price: Optional[Decimal] = None,
            time_in_force: Optional[TimeInForce] = None,
            client_id: Optional[str] = None,
            test: bool = True) -> OrderResult:
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, id_: int) -> Any:
        pass
