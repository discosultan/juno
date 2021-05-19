from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterable, AsyncIterator

from juno.candles.models import Candle


class Exchange(ABC):
    can_stream_historical_candles: bool = False
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False

    @abstractmethod
    def map_candle_intervals(self) -> dict[int, int]:  # interval: offset
        pass

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        raise TypeError()
        yield

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        raise TypeError()
        yield
