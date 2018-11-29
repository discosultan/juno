import asyncio
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

from .sqlite import SQLite


class Memory(SQLite):
    """In-memory data storage. Uses SQLite's memory mode for implementation."""

    def __init__(self):
        super().__init__()
        self._dbs = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.gather(*(db.__aexit__(exc_type, exc, tb) for db in self._dbs.values()))

    @asynccontextmanager
    async def _get_db(self, name: str) -> Any:
        db = self._dbs.get(name)
        if not db:
            db = aiosqlite.connect(':memory:')
            await db.__aenter__()
            self._dbs[name] = db
        yield db
