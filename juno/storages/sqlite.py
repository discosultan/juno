from contextlib import asynccontextmanager
# import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

import aiosqlite

from juno import Candle, Span


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

    async def stream_candle_spans(self, exchange, symbol, start, end):
        _log.info(f'streaming candle span(s) from {self.__class__.__name__}')
        async with self._get_db(exchange) as db:
            table = await self._get_table(db, Span, prefix=_symbol(symbol))
            query = f'SELECT * FROM {table} WHERE start < ? AND end > ? ORDER BY start'
            async with db.execute(query, [end, start]) as cursor:
                async for row in cursor:
                    yield Span(*row)

    async def stream_candles(self, exchange, symbol, start, end):
        _log.info(f'streaming candle(s) from {self.__class__.__name__}')
        async with self._get_db(exchange) as db:
            table = await self._get_table(db, Candle, prefix=_symbol(symbol))
            query = f'SELECT * FROM {table} WHERE time >= ? AND time < ? ORDER BY time'
            async with db.execute(query, [start, end]) as cursor:
                async for row in cursor:
                    yield Candle(*row)

    async def store_candles_and_span(self, exchange, symbol, interval, candles, span):
        if span.start > candles[0].time or span.end <= candles[-1].time:
            raise ValueError('invalid input')

        _log.info(f'storing {len(candles)} candle(s) for span ({span}) to '
                  f'{self.__class__.__name__}')
        async with self._get_db(exchange) as db:
            try:
                table = await self._get_table(db, Candle, prefix=_symbol(symbol))
                await db.executemany(
                    f'INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)',
                    [[*candle] for candle in candles])
            except sqlite3.IntegrityError as err:
                # TODO: Can we relax this constraint?
                _log.error(f'{err} ({self._exchange_name}, {self.asset_pair}, {self.interval})')
                raise
            table = await self._get_table(db, Span, prefix=_symbol(symbol))
            await db.execute(f'INSERT INTO {table} VALUES (?, ?)', [*span])
            await db.commit()

    # async def get_asset_pair_info(self):
    #     _log.debug(f'getting asset pair info from {self._name}')
    #     async with self._get_db() as db:
    #         cursor = await db.execute(
    #           'SELECT value FROM AssetPairInfo ORDER BY time DESC LIMIT 1')
    #         result = await cursor.fetchone()
    #         return result if result is None else AssetPairInfo(*json.loads(result[0]))

    # async def store_asset_pair_info(self, val):
    #     _log.debug(f'storing asset pair info to {self._name}')
    #     async with self._get_db() as db:
    #         await db.execute(
    #           'INSERT INTO AssetPairInfo VALUES (?, ?)', [val.time, json.dumps(val)])
    #         await db.commit()

    # async def get_account_info(self):
    #     _log.debug(f'getting account info info from {self._name}')
    #     async with self._get_db() as db:
    #         cursor = await db.execute('SELECT value FROM AccountInfo ORDER BY time DESC LIMIT 1')
    #         result = await cursor.fetchone()
    #         return result if result is None else AccountInfo(*json.loads(result[0]))

    # async def store_account_info(self, val):
    #     _log.debug(f'storing account info to {self._name}')
    #     async with aiosqlite.connect(self._db_name) as db:
    #         await db.execute(
    #           'INSERT INTO AccountInfo VALUES (?, ?)', [val.time, json.dumps(val)])
    #         await db.commit()

    @asynccontextmanager
    async def _get_db(self, name: str) -> Any:
        name = str(_get_home().joinpath(f'v{_VERSION}_{name}.db'))
        async with aiosqlite.connect(name) as db:
            yield db

    async def _get_table(self, db: Any, type: type, prefix: str = '') -> str:
        name = prefix + type.__name__
        tables = self._tables.get(db)
        if not tables:
            tables = set()
            self._tables[db] = tables
        if name not in tables:
            await db.execute(type_to_create_query(name, type))
            await db.commit()
            tables.add(name)
        return name


def type_to_create_query(name: str, table_type: type) -> str:
    cols = []
    print(table_type.__annotations__)
    for i, (col_name, col_type) in enumerate(table_type.__annotations__.items()):
        col_sql_type = type_to_sql_type(col_type)
        col_constrain = 'PRIMARY KEY' if i == 0 else 'NOT NULL'
        cols.append(f'{col_name} {col_sql_type} {col_constrain}')
    return f'CREATE TABLE IF NOT EXISTS {name} ({", ".join(cols)})'


def type_to_sql_type(type: type) -> str:
    if type == int:
        return 'INTEGER'
    if type == float:
        return 'REAL'
    raise NotImplementedError()

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


def _symbol(symbol):
    return symbol.replace('-', '').upper()


def _get_home():
    path = Path(Path.home(), '.juno')
    path.mkdir(parents=True, exist_ok=True)
    return path
