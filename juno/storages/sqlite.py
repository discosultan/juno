import asyncio
import logging
import sqlite3
from collections import defaultdict
from contextlib import closing
from decimal import Decimal
from typing import (
    Any, AsyncIterable, ContextManager, Dict, List, NamedTuple, Optional, Set, Tuple, Type,
    TypeVar, Union, get_type_hints
)

from juno import Interval, Timestamp, json
from juno.time import strfspan
from juno.typing import raw_to_type
from juno.utils import home_path

from .storage import Storage

_log = logging.getLogger(__name__)

# Version should be incremented every time a storage schema changes.
_VERSION = '40'

T = TypeVar('T')

Primitive = Union[bool, int, float, Decimal, str]


def _serialize_decimal(d: Decimal) -> bytes:
    return str(d).encode('ascii')


def _deserialize_decimal(s: bytes) -> Decimal:
    return Decimal(s.decode('ascii'))


sqlite3.register_adapter(Decimal, _serialize_decimal)
sqlite3.register_converter('DECIMAL', _deserialize_decimal)

sqlite3.register_adapter(bool, int)
sqlite3.register_converter('BOOLEAN', lambda v: bool(int(v)))


class SQLite(Storage):
    def __init__(self, version: Optional[str] = None) -> None:
        self._version = version if version is not None else _VERSION
        self._tables: Dict[Any, Set[str]] = defaultdict(set)
        _log.info(f'sqlite version: {sqlite3.sqlite_version}; schema version: {_VERSION}')

    async def stream_time_series_spans(
        self, shard: str, key: str, start: int, end: int
    ) -> AsyncIterable[Tuple[int, int]]:
        def inner() -> List[Tuple[int, int]]:
            _log.info(
                f'from shard {shard} {key} streaming span(s) between {strfspan(start, end)}'
            )
            with self._connect(shard) as conn:
                span_key = f'{key}_{SPAN_KEY}'
                self._ensure_table(conn, span_key, Span)
                return conn.execute(
                    f'SELECT * FROM {span_key} WHERE start < ? AND end > ? ORDER BY start',
                    [end, start]
                ).fetchall()

        rows = await asyncio.get_running_loop().run_in_executor(None, inner)
        for span_start, span_end in rows:
            yield max(span_start, start), min(span_end, end)

    async def stream_time_series(
        self, shard: str, key: str, type_: Type[T], start: int, end: int
    ) -> AsyncIterable[T]:
        def inner() -> List[T]:
            _log.info(
                f'from shard {shard} {key} streaming items between {strfspan(start, end)}'
            )
            with self._connect(shard) as conn:
                self._ensure_table(conn, key, type_)
                return conn.execute(
                    f'SELECT * FROM {key} WHERE time >= ? AND time < ? ORDER BY time',
                    [start, end]
                ).fetchall()
        rows = await asyncio.get_running_loop().run_in_executor(None, inner)
        for row in rows:
            yield raw_to_type(row, type_)

    async def store_time_series_and_span(
        self, shard: str, key: str, items: List[Any], start: int, end: int
    ) -> None:
        # Even if items list is empty, we still want to store a span for the period!

        if len(items) > 0:
            type_ = type(items[0])
            if start > items[0].time:
                raise ValueError(f'Span start {start} bigger than first item time {items[0].time}')
            if end <= items[-1].time:
                raise ValueError(
                    f'Span end {end} smaller than or equal to last item time {items[-1].time}'
                )

        def inner() -> None:
            _log.info(
                f'to shard {shard} {key} inserting {len(items)} item(s) between '
                f'{strfspan(start, end)}'
            )
            span_key = f'{key}_{SPAN_KEY}'
            with self._connect(shard) as conn:
                self._ensure_table(conn, span_key, Span)
                if len(items) > 0:
                    self._ensure_table(conn, key, type_)

                c = conn.cursor()
                if len(items) > 0:
                    try:
                        c.executemany(
                            f'INSERT INTO {key} '
                            f'VALUES ({", ".join(["?"] * len(get_type_hints(type_)))})',
                            items
                        )
                    except sqlite3.IntegrityError as err:
                        # TODO: Can we relax this constraint?
                        _log.error(f'{err} {shard} {key}')
                        raise
                c.execute(f'INSERT INTO {span_key} VALUES (?, ?)', [start, end])
                conn.commit()

        await asyncio.get_running_loop().run_in_executor(None, inner)

    async def get_item(self, shard: str, key: str, type_: Type[T]) -> Optional[T]:
        def inner() -> Optional[T]:
            _log.info(f'from shard {shard} getting {key}')
            with self._connect(shard) as conn:
                self._ensure_table(conn, KEY_VALUE_PAIR_KEY, KeyValuePair)
                row = conn.execute(
                    f'SELECT * FROM {KEY_VALUE_PAIR_KEY} WHERE key=?', [key]
                ).fetchone()
                return raw_to_type(json.loads(row[1]), type_) if row else None

        return await asyncio.get_running_loop().run_in_executor(None, inner)

    async def set_item(self, shard: str, key: str, item: T) -> None:
        def inner() -> None:
            _log.info(f'to shard {shard} setting {key}')
            with self._connect(shard) as conn:
                self._ensure_table(conn, KEY_VALUE_PAIR_KEY, KeyValuePair)
                conn.execute(
                    f'INSERT OR REPLACE INTO {KEY_VALUE_PAIR_KEY} VALUES (?, ?)',
                    [key, json.dumps(item)]
                )
                conn.commit()

        await asyncio.get_running_loop().run_in_executor(None, inner)

    def _connect(self, shard: str) -> ContextManager[sqlite3.Connection]:
        path = str(home_path('data') / f'v{self._version}_{shard}.db')
        _log.debug(f'opening shard {path}')
        return closing(sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES))

    def _ensure_table(self, conn: sqlite3.Connection, name: str, type_: Type[Any]) -> None:
        tables = self._tables[conn]
        if name not in tables:
            c = conn.cursor()
            _create_table(c, type_, name)
            conn.commit()
            tables.add(name)


def _create_table(c: sqlite3.Cursor, type_: Type[Any], name: str) -> None:
    type_hints = get_type_hints(type_)
    col_types = [(k, _type_to_sql_type(v)) for k, v in type_hints.items()]

    # Create table.
    cols = []
    for col_name, col_type in col_types:
        cols.append(f'{col_name} {col_type} NOT NULL')
    c.execute(f'CREATE TABLE IF NOT EXISTS {name} ({", ".join(cols)})')

    # Add indices.
    meta_getter = getattr(type_, 'meta', None)
    meta = meta_getter() if meta_getter else None
    if meta:
        for cname, ctype in meta.items():
            if ctype == 'index':
                c.execute(f'CREATE INDEX IF NOT EXISTS {name}Index ON {name}({cname})')
            elif ctype == 'unique':
                c.execute(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS {name}UniqueIndex ON {name}({cname})'
                )
            else:
                raise NotImplementedError()

    # Create debug views.
    view_cols = []
    create_view = False
    for col_name, type_ in type_hints.items():
        if type_ is Timestamp:
            view_cols.append(
                f"strftime('%Y-%m-%d %H:%M:%S', {col_name} / 1000, 'unixepoch') AS {col_name}"
            )
            create_view = True
        else:
            view_cols.append(col_name)
    if create_view:
        c.execute(
            f'CREATE VIEW IF NOT EXISTS {name}View AS '
            f'SELECT {", ".join(view_cols)} FROM {name}'
        )


def _type_to_sql_type(type_: Type[Primitive]) -> str:
    if type_ in [Interval, Timestamp, int]:
        return 'INTEGER'
    if type_ is float:
        return 'REAL'
    if type_ is Decimal:
        return 'DECIMAL'
    if type_ is str:
        return 'TEXT'
    if type_ is bool:
        return 'BOOLEAN'
    raise NotImplementedError(f'Missing conversion for type {type_}')


class KeyValuePair(NamedTuple):
    key: str
    value: str

    @staticmethod
    def meta() -> Dict[str, str]:
        return {
            'key': 'unique',
        }


class Span(NamedTuple):
    start: Timestamp
    end: Timestamp

    @staticmethod
    def meta() -> Dict[str, str]:
        return {
            'start': 'unique',
            'end': 'unique',
        }


KEY_VALUE_PAIR_KEY = KeyValuePair.__name__.lower()
SPAN_KEY = Span.__name__.lower()
