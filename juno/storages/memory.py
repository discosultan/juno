from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from typing import Dict

from aiosqlite import Connection, connect

from juno.typing import ExcType, ExcValue, Traceback

from .sqlite import SQLite


class Memory(SQLite):
    """In-memory data storage. Uses SQLite's memory mode for implementation."""

    def __init__(self) -> None:
        super().__init__()
        self._dbs: Dict[str, Connection] = {}

    async def __aenter__(self) -> Memory:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(*(db.__aexit__(exc_type, exc, tb) for db in self._dbs.values()))

    @asynccontextmanager
    async def _connect(self, key: str) -> Connection:
        db = self._dbs.get(key)
        if not db:
            db = connect(':memory:', detect_types=sqlite3.PARSE_DECLTYPES)
            await db.__aenter__()
            self._dbs[key] = db
        yield db
