from __future__ import annotations

import asyncio
import sqlite3
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from aiosqlite import Connection, connect

from juno.typing import ExcType, ExcValue, Traceback

from .sqlite import SQLite


class Memory(SQLite):
    """In-memory data storage. Uses SQLite's memory mode for implementation."""

    def __init__(self) -> None:
        super().__init__()
        self._db_ctxs: Dict[str, _DBContext] = defaultdict(_DBContext)

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(
            *(ctx.connection.__aexit__(exc_type, exc, tb)
              for ctx in self._db_ctxs.values() if ctx.connection))

    @asynccontextmanager
    async def _connect(self, key: Any) -> AsyncIterator[Connection]:
        name = self._normalize_key(key)
        ctx = self._db_ctxs[name]
        async with ctx.lock:
            if not ctx.connection:
                ctx.connection = connect(':memory:', detect_types=sqlite3.PARSE_DECLTYPES)
                await ctx.connection.__aenter__()
        yield ctx.connection


class _DBContext:

    def __init__(self) -> None:
        self.connection: Optional[Connection] = None
        self.lock = asyncio.Lock()
