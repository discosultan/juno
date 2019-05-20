from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple, Type, Union

from juno import Candle, Span

Key = Union[str, Tuple[Any, ...]]


class Storage(AbstractAsyncContextManager):

    @abstractmethod
    async def stream_candle_spans(self, key: Key, start: int, end: int) -> AsyncIterable[Span]:
        yield  # type: ignore

    @abstractmethod
    async def stream_candles(self, key: Key, start: int, end: int) -> AsyncIterable[Candle]:
        yield  # type: ignore

    @abstractmethod
    async def store_candles_and_span(self, key: Key, candles: List[Candle], start: int, end: int
                                     ) -> None:
        pass

    @abstractmethod
    async def get_map(self, key: Key, type_: Type[Any]
                      ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
        pass

    @abstractmethod
    async def set_map(self, key: Key, type_: Type[Any], items: Dict[str, Any]) -> None:
        pass
