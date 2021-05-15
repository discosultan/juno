from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterable, AsyncIterator

from juno.exchanges import Exchange as Session
from juno.trades import Trade, exchanges


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
