from __future__ import annotations

import asyncio
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from threading import Lock
from typing import Dict, Iterator, Optional

from juno.typing import ExcType, ExcValue, Traceback

from .sqlite import SQLite


class Memory(SQLite):
    """In-memory data storage. Uses SQLite's memory mode for implementation."""
    def __init__(self) -> None:
        super().__init__()
        self._conns: Dict[str, _ConnectionContext] = defaultdict(_ConnectionContext)

    async def __aenter__(self) -> Memory:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        def inner():
            for ctx in self._conns.values():
                assert ctx.connection
                ctx.connection.close()
        await asyncio.get_running_loop().run_in_executor(None, inner)

    @contextmanager
    def _connect(self, shard: str) -> Iterator[sqlite3.Connection]:
        ctx = self._conns[shard]
        with ctx.lock:
            if not ctx.connection:
                conn = sqlite3.connect(
                    ':memory:',
                    detect_types=sqlite3.PARSE_DECLTYPES,
                    check_same_thread=False
                )
                ctx.connection = conn
            yield ctx.connection


class _ConnectionContext:
    def __init__(self) -> None:
        self.connection: Optional[sqlite3.Connection] = None
        self.lock = Lock()
