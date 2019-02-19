from abc import ABC, abstractmethod
from typing import Any, Dict, AsyncIterable, Tuple

from juno import Balance, Candle, SymbolInfo


class Exchange(ABC):

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
        yield  # type: ignore
