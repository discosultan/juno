from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterable, AsyncIterator

from juno.orderbook import Depth


class Exchange(ABC):
    # Capabilities.
    can_stream_depth_snapshot: bool = False  # Streams snapshot as first depth WS message.

    @abstractmethod
    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        pass

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        yield  # type: ignore
