from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import (Any, AsyncIterable, AsyncIterator, Dict, List, Optional, Set, Tuple,
                    get_type_hints)

import simplejson as json
from aiosqlite import Connection, connect

from juno import Candle, Span
from juno.time import time_ms
from juno.typing import ExcType, ExcValue, Traceback

_log = logging.getLogger(__name__)

# Version should be incremented every time a storage schema changes.
_VERSION = 7


def _serialize_decimal(d: Decimal) -> bytes:
    return str(d).encode('ascii')


def _deserialize_decimal(s: bytes) -> Decimal:
    return Decimal(s.decode('ascii'))


sqlite3.register_adapter(Decimal, _serialize_decimal)
sqlite3.register_converter('DECIMAL', _deserialize_decimal)


class SQLite:

    def __init__(self) -> None:
        self._tables: Dict[Any, Set[type]] = {}

    async def __aenter__(self) -> SQLite:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    async def stream_candle_spans(self, key: Any, start: int, end: int) -> AsyncIterable[Span]:
        _log.info(f'streaming candle span(s) between {Span(start, end)}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Span)
            query = f'SELECT * FROM {Span.__name__} WHERE start < ? AND end > ? ORDER BY start'
            async with db.execute(query, [end, start]) as cursor:
                async for span_start, span_end in cursor:
                    yield Span(max(span_start, start), min(span_end, end))

    async def stream_candles(self, key: Any, start: int, end: int) -> AsyncIterable[Candle]:
        _log.info(f'streaming candle(s) between {Span(start, end)}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Candle)
            query = f'SELECT * FROM {Candle.__name__} WHERE time >= ? AND time < ? ORDER BY time'
            async with db.execute(query, [start, end]) as cursor:
                async for row in cursor:
                    yield Candle(*row)

    async def store_candles_and_span(self, key: Any, candles: List[Candle], start: int, end: int
                                     ) -> None:
        if start > candles[0].time or end <= candles[-1].time:
            raise ValueError('Invalid input')

        _log.info(f'storing {len(candles)} candle(s) between {Span(start, end)}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Candle)
            try:
                await db.executemany(
                    f'INSERT INTO {Candle.__name__} VALUES (?, ?, ?, ?, ?, ?)',
                    candles)
            except sqlite3.IntegrityError as err:
                # TODO: Can we relax this constraint?
                _log.error(f'{err} {key}')
                raise
            await self._ensure_table(db, Span)
            await db.execute(f'INSERT INTO {Span.__name__} VALUES (?, ?)', [start, end])
            await db.commit()

    async def get_map(self, key: Any, item_cls: type
                      ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
        cls_name = item_cls.__name__
        _log.info(f'getting map of {cls_name}s')
        async with self._connect(key) as db:
            await self._ensure_table(db, Bag)
            cursor = await db.execute(f'SELECT * FROM {Bag.__name__} WHERE key=?',
                                      ['map_' + cls_name])
            row = await cursor.fetchone()
            await cursor.close()
            if row:
                return {k: item_cls(**v) for k, v
                        in json.loads(row[1], use_decimal=True).items()}, row[2]
            else:
                return None, None

    # TODO: Generic type
    async def set_map(self, key: Any, item_cls: type, items: Dict[str, Any]) -> None:
        cls_name = item_cls.__name__
        _log.info(f'setting map of {len(items)} {cls_name}s')
        async with self._connect(key) as db:
            await self._ensure_table(db, Bag)
            await db.execute(f'INSERT OR REPLACE INTO {Bag.__name__} VALUES (?, ?, ?)',
                             ['map_' + cls_name, json.dumps(items, use_decimal=True), time_ms()])
            await db.commit()

    @asynccontextmanager
    async def _connect(self, key: Any) -> AsyncIterator[Connection]:
        name = _normalize_key(key)
        _log.info(f'connecting to {key}')
        name = str(_get_home().joinpath(f'v{_VERSION}_{name}.db'))
        async with connect(name, detect_types=sqlite3.PARSE_DECLTYPES) as db:
            yield db

    async def _ensure_table(self, db: Any, type: type) -> None:
        tables = self._tables.get(db)
        if not tables:
            tables = set()
            self._tables[db] = tables
        if type not in tables:
            await _create_table(db, type)
            await db.commit()
            tables.add(type)


def _normalize_key(key: Any) -> str:
    key_type = type(key)
    if key_type is str:
        # The type is already known to be str but this is to please mypy.
        return str(key)
    elif key_type is tuple:
        return '_'.join(map(str, key))
    else:
        raise NotImplementedError()


def _get_home() -> Path:
    path = Path(Path.home(), '.juno')
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _create_table(db: Any, type: type) -> None:
    annotations = get_type_hints(type)
    col_names = list(annotations.keys())
    col_types = [_type_to_sql_type(t) for t in annotations.values()]
    cols = []
    for i in range(0, len(col_names)):
        col_constrain = 'PRIMARY KEY' if i == 0 else 'NOT NULL'
        cols.append(f'{col_names[i]} {col_types[i]} {col_constrain}')
    await db.execute(f'CREATE TABLE IF NOT EXISTS {type.__name__} ({", ".join(cols)})')

    # TODO: Use typing instead based on NewType()
    VIEW_COL_NAMES = ['time', 'start', 'end']
    if any((n for n in col_names if n in VIEW_COL_NAMES)):
        view_cols = []
        for col in col_names:
            if col in VIEW_COL_NAMES:
                view_cols.append(
                    f"strftime('%Y-%m-%d %H:%M:%S', {col} / 1000, 'unixepoch') AS {col}")
            else:
                view_cols.append(col)

        await db.execute(f'CREATE VIEW IF NOT EXISTS {type.__name__}View AS '
                         f'SELECT {", ".join(view_cols)} FROM {type.__name__}')


def _type_to_sql_type(type_: type) -> str:
    if type_ is int:
        return 'INTEGER'
    if type_ is float:
        return 'REAL'
    if type_ is Decimal:
        return 'DECIMAL'
    if type_ is str:
        return 'TEXT'
    raise NotImplementedError(f'Missing conversion for type {type_}')


class Bag:
    key: str
    value: str
    time: int
