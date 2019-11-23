from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator

from juno.typing import ExcType, ExcValue, Traceback

from .sqlite import SQLite


class Memory(SQLite):
    """In-memory data storage. Uses SQLite's memory mode for implementation."""
    def __init__(self) -> None:
        super().__init__()
        self._db_conns: Dict[str, sqlite3.Connection] = {}

    async def __aenter__(self) -> Memory:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        def inner() -> None:
            for conn in self._db_conns.values():
                conn.close()

        await asyncio.get_running_loop().run_in_executor(None, inner)

    @contextmanager
    def _connect(self, key: Any) -> Iterator[sqlite3.Connection]:
        name = self._normalize_key(key)
        conn = self._db_conns.get(name)
        if not conn:
            conn = sqlite3.connect(
                ':memory:',
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False
            )
            self._db_conns[name] = conn
        yield conn
