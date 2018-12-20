from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, List, Tuple

import aiosqlite

from juno import Candle, Span
from juno.time import time_ms


_log = logging.getLogger(__package__)


# Version should be incremented every time a storage schema changes.
_VERSION = 1


class SQLite:

    def __init__(self):
        self._tables = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def stream_candle_spans(self, key: Any, start: int, end: int) -> Any:
        _log.info(f'streaming candle span(s) from {self.__class__.__name__}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Span)
            query = f'SELECT * FROM {Span.__name__} WHERE start < ? AND end > ? ORDER BY start'
            async with db.execute(query, [end, start]) as cursor:
                async for span_start, span_end in cursor:
                    yield max(span_start, start), min(span_end, end)

    async def stream_candles(self, key: Any, start: int, end: int) -> Any:
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

    async def get(self, key: Any, item_cls: type) -> Tuple[Any, int]:
        cls_name = item_cls.__name__
        _log.info(f'getting {cls_name} from {self.__class__.__name__}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Bag)
            cursor = await db.execute(f'SELECT * FROM {Bag.__name__} WHERE key=?', [cls_name])
            row = await cursor.fetchone()
            await cursor.close()
            if row:
                return item_cls(*json.loads(row[1])), row[2]
            else:
                return None, None

    async def store(self, key: Any, item: Any):
        cls_name = item.__class__.__name__
        _log.info(f'storing {cls_name} to {self.__class__.__name__}')
        async with self._connect(key) as db:
            await self._ensure_table(db, Bag)
            await db.execute(f'INSERT OR REPLACE INTO {Bag.__name__} VALUES (?, ?, ?)',
                             [cls_name, json.dumps(item), time_ms()])
            await db.commit()

    @asynccontextmanager
    async def _connect(self, key: Any) -> Any:
        key_type = type(key)
        if key_type is str:
            name = key
        elif key_type is tuple:
            name = '_'.join(map(str, key))
        else:
            raise NotImplementedError()

        name = str(_get_home().joinpath(f'v{_VERSION}_{name}.db'))
        async with aiosqlite.connect(name) as db:
            yield db

    async def _ensure_table(self, db: Any, type: type) -> None:
        tables = self._tables.get(db)
        if not tables:
            tables = set()
            self._tables[db] = tables
        if type not in tables:
            await db.execute(_type_to_create_query(type))
            await db.commit()
            tables.add(type)


def _get_home():
    path = Path(Path.home(), '.juno')
    path.mkdir(parents=True, exist_ok=True)
    return path


def _type_to_create_query(type: type) -> str:
    cols = []
    for i, (col_name, col_type) in enumerate(type.__annotations__.items()):
        col_sql_type = _type_to_sql_type(col_type)
        col_constrain = 'PRIMARY KEY' if i == 0 else 'NOT NULL'
        cols.append(f'{col_name} {col_sql_type} {col_constrain}')
    return f'CREATE TABLE IF NOT EXISTS {type.__name__} ({", ".join(cols)})'


def _type_to_sql_type(type: type) -> str:
    if type == int:
        return 'INTEGER'
    if type == float:
        return 'REAL'
    if type == str:
        return 'TEXT'
    raise NotImplementedError()


class Bag:
    key: str
    value: str
    time: int

# async def _ensure_tables_exist(self):
#     async with aiosqlite.connect(self._db_name) as db:
#         await asyncio.gather(
#             db.execute('''
#                 CREATE TABLE IF NOT EXISTS Candle (
#                     time INTEGER PRIMARY KEY,
#                     open REAL NOT NULL,
#                     high REAL NOT NULL,
#                     low REAL NOT NULL,
#                     close REAL NOT NULL,
#                     volume REAL NOT NULL
#                 )'''),
#             db.execute('''
#                 CREATE TABLE IF NOT EXISTS Span (
#                     start INTEGER PRIMARY KEY,
#                     end INTEGER NOT NULL
#                 )'''),
#             db.execute('''
#                 CREATE TABLE IF NOT EXISTS AssetPairInfo (
#                     time INTEGER PRIMARY KEY,
#                     value TEXT NOT NULL
#                 )'''),
#             db.execute('''
#                 CREATE TABLE IF NOT EXISTS AccountInfo (
#                     time INTEGER PRIMARY KEY,
#                     value TEXT NOT NULL
#                 )'''))
#         # Simplify debugging through these views.
#         await asyncio.gather(
#             db.execute('''
#                 CREATE VIEW IF NOT EXISTS CandleView AS SELECT
#                     strftime('%Y-%m-%d %H:%M:%S', time / 1000, 'unixepoch') AS time_str,
#                     time,
#                     open,
#                     high,
#                     low,
#                     close,
#                     volume
#                 FROM Candle'''),
#             db.execute('''
#                 CREATE VIEW IF NOT EXISTS CandleRangeView AS SELECT
#                     strftime('%Y-%m-%d %H:%M:%S', start / 1000, 'unixepoch') AS start_str,
#                     start,
#                     strftime('%Y-%m-%d %H:%M:%S', end / 1000, 'unixepoch') AS end_str,
#                     end
#                 FROM Span'''))
#         await db.commit()
