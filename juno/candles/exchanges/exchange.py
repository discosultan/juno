from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterable, AsyncIterator

from juno.candles import exchanges
from juno.candles.models import Candle
from juno.exchanges import Exchange as Session


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

    @staticmethod
    def from_session(session: Session) -> Exchange:
        return next(
            t(session)
            for n, t in _list_exchange_members()
            if n == type(session).__name__
        )

    @staticmethod
    def map_from_sessions(sessions: list[Session]) -> dict[str, Exchange]:
        type_sessions = {type(s).__name__: s for s in sessions}
        return {
            n.lower(): t(type_sessions[n])
            for n, t in _list_exchange_members()
            if n in type_sessions
        }


def _list_exchange_members() -> list[tuple[str, type]]:
    return inspect.getmembers(
        exchanges,
        lambda m: inspect.isclass(m) and m is not Exchange and issubclass(m, Exchange),
    )
