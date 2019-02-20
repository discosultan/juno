from __future__ import annotations
from contextlib import asynccontextmanager
from decimal import Decimal
import logging
from pathlib import Path
import sqlite3
from typing import (Any, AsyncIterable, AsyncIterator, Dict, get_type_hints, List, Optional, Set,
                    Tuple)

from aiosqlite import connect, Connection
import simplejson as json

from juno import Candle, Span
from juno.time import time_ms


_log = logging.getLogger(__name__)


# Version should be incremented every time a storage schema changes.
_VERSION = 1


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

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass

    async def stream_candle_spans(self, key: Any, start: int, end: int) -> AsyncIterable[Span]:
        _log.info(f'streaming candle span(s) from {self.__class__.__name__}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Span)
            query = f'SELECT * FROM {Span.__name__} WHERE start < ? AND end > ? ORDER BY start'
            async with db.execute(query, [end, start]) as cursor:
                async for span_start, span_end in cursor:
                    yield Span(max(span_start, start), min(span_end, end))

    async def stream_candles(self, key: Any, start: int, end: int) -> AsyncIterable[Candle]:
        _log.info(f'streaming candle(s) from {self.__class__.__name__}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Candle)
            query = f'SELECT * FROM {Candle.__name__} WHERE time >= ? AND time < ? ORDER BY time'
            async with db.execute(query, [start, end]) as cursor:
                async for row in cursor:
                    yield Candle(*row)

    async def store_candles_and_span(self, key: Any, candles: List[Candle], start: int, end: int
                                     ) -> Any:
        if start > candles[0].time or end <= candles[-1].time:
            raise ValueError('invalid input')

        _log.info(f'storing {len(candles)} candle(s) for {Span(start, end)} to '
                  f'{self.__class__.__name__}')
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

    async def get(self, key: Any, item_cls: type) -> Tuple[Optional[Any], Optional[int]]:
        cls_name = item_cls.__name__
        _log.info(f'getting {cls_name} from {self.__class__.__name__}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Bag)
            cursor = await db.execute(f'SELECT * FROM {Bag.__name__} WHERE key=?', [cls_name])
            row = await cursor.fetchone()
            await cursor.close()
            if row:
                return item_cls(**json.loads(row[1])), row[2]
            else:
                return None, None

    async def store(self, key: Any, item: Any) -> None:
        cls_name = item.__class__.__name__
        _log.info(f'storing {cls_name} to {self.__class__.__name__}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Bag)
            await db.execute(f'INSERT OR REPLACE INTO {Bag.__name__} VALUES (?, ?, ?)',
                             [cls_name, json.dumps(item), time_ms()])
            await db.commit()

    @asynccontextmanager
    async def _connect(self, key: Any) -> AsyncIterator[Connection]:
        key_type = type(key)
        if key_type is str:
            name = key
        elif key_type is tuple:
            name = '_'.join(map(str, key))
        else:
            raise NotImplementedError()

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


def _type_to_sql_type(type: type) -> str:
    if type is int:
        return 'INTEGER'
    if type is float:
        return 'REAL'
    if type is Decimal:
        return 'DECIMAL'
    if type is str:
        return 'TEXT'
    raise NotImplementedError(f'Missing conversion for type {type}')


class Bag:
    key: str
    value: str
    time: int
