from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple, Type, TypeVar, Union

T = TypeVar('T')

Key = Union[str, Tuple[Any, ...]]


class Storage(ABC):
    @abstractmethod
    async def stream_time_series_spans(self, key: Key, type: Type[T], start: int,
                                       end: int) -> AsyncIterable[Tuple[int, int]]:
        yield  # type: ignore

    @abstractmethod
    async def stream_time_series(self, key: Key, type: Type[T], start: int,
                                 end: int) -> AsyncIterable[T]:
        yield  # type: ignore

    @abstractmethod
    async def store_time_series_and_span(
        self, key: Key, type: Type[Any], items: List[Any], start: int, end: int
    ) -> None:
        pass

    @abstractmethod
    async def get(self, key: Key, type_: Type[T]) -> Tuple[Optional[T], Optional[int]]:
        pass

    @abstractmethod
    async def set(self, key: Key, type_: Type[T], item: T) -> None:
        pass

    @abstractmethod
    async def get_map(self, key: Key,
                      type_: Type[T]) -> Tuple[Optional[Dict[str, T]], Optional[int]]:
        pass

    @abstractmethod
    async def set_map(self, key: Key, type_: Type[T], items: Dict[str, T]) -> None:
        pass
