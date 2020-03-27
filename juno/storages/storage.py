from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterable, List, Optional, Tuple, Type, TypeVar

T = TypeVar('T')


class Storage(ABC):
    @abstractmethod
    async def stream_time_series_spans(
        self, shard: str, key: str, start: int, end: int
    ) -> AsyncIterable[Tuple[int, int]]:
        yield  # type: ignore

    @abstractmethod
    async def stream_time_series(
        self, shard: str, key: str, type_: Type[T], start: int, end: int
    ) -> AsyncIterable[T]:
        yield  # type: ignore

    @abstractmethod
    async def store_time_series_and_span(
        self, shard: str, key: str, items: List[Any], start: int, end: int
    ) -> None:
        pass

    @abstractmethod
    async def get_item(self, shard: str, key: str, type_: Type[T]) -> Optional[T]:
        pass

    @abstractmethod
    async def set_item(self, shard: str, key: str, item: T) -> None:
        pass
