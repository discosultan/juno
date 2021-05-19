from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterable, AsyncIterator

from juno.trades.models import Trade


class Exchange(ABC):
    @abstractmethod
    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        yield  # type: ignore

    @abstractmethod
    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        yield  # type: ignore
