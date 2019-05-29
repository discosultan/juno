from __future__ import annotations

from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple, Type, TypeVar, Union

from juno import Candle, Span
from juno.typing import ExcType, ExcValue, Traceback

T = TypeVar('T')

Key = Union[str, Tuple[Any, ...]]


class Storage(AbstractAsyncContextManager):

    async def __aenter__(self) -> Storage:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

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
    async def get_map(self, key: Key, type_: Type[T]
                      ) -> Tuple[Optional[Dict[str, T]], Optional[int]]:
        pass

    @abstractmethod
    async def set_map(self, key: Key, type_: Type[T], items: Dict[str, T]) -> None:
        pass
