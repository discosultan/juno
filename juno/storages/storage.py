from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterable, Optional, TypeVar

from juno import Timestamp
from juno.contextlib import AsyncContextManager

T = TypeVar("T")


class Storage(AsyncContextManager, ABC):
    @abstractmethod
    async def stream_time_series_spans(
        self, shard: str, key: str, start: Timestamp, end: Timestamp
    ) -> AsyncIterable[tuple[int, int]]:
        yield  # type: ignore

    @abstractmethod
    async def stream_time_series(
        self, shard: str, key: str, type_: type[T], start: Timestamp, end: Timestamp
    ) -> AsyncIterable[T]:
        yield  # type: ignore

    @abstractmethod
    async def store_time_series_and_span(
        self, shard: str, key: str, items: list[Any], start: Timestamp, end: Timestamp
    ) -> None:
        pass

    @abstractmethod
    async def get(self, shard: str, key: str, type_: type[T]) -> Optional[T]:
        pass

    @abstractmethod
    async def set(self, shard: str, key: str, item: T) -> None:
        pass

    @staticmethod
    def key(*items: Any) -> str:
        return "_".join(map(str, items))
