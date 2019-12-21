import asyncio
import logging
import sqlite3
from collections import defaultdict
from contextlib import closing
from decimal import Decimal
from typing import (
    Any, AsyncIterable, ContextManager, Dict, List, Optional, Set, Tuple, Type, TypeVar, Union,
    cast, get_args, get_origin, get_type_hints
)

import juno.json as json
from juno.time import strfspan, time_ms
from juno.typing import get_name, isnamedtuple
from juno.utils import home_path

from .storage import Storage

_log = logging.getLogger(__name__)

# Version should be incremented every time a storage schema changes.
_VERSION = '32'

T = TypeVar('T')

Key = Union[str, Tuple[Any, ...]]
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

    async def stream_time_series_spans(self, key: Key, type: Type[T], start: int,
                                       end: int) -> AsyncIterable[Tuple[int, int]]:
        def inner() -> List[Tuple[int, int]]:
            _log.info(
                f'streaming {type.__name__} span(s) between {strfspan(start, end)} from {key} db'
            )
            with self._connect(key) as conn:
                span_table_name = f'{type.__name__}{Span.__name__}'
                self._ensure_table(conn, Span, span_table_name)
                return conn.execute(
                    f'SELECT * FROM {span_table_name} WHERE start < ? AND end > ? ORDER BY start',
                    [end, start]
                ).fetchall()

        rows = await asyncio.get_running_loop().run_in_executor(None, inner)
        for span_start, span_end in rows:
            yield max(span_start, start), min(span_end, end)

    async def stream_time_series(self, key: Key, type: Type[T], start: int,
                                 end: int) -> AsyncIterable[T]:
        def inner() -> List[T]:
            _log.info(f'streaming {type.__name__}(s) between {strfspan(start, end)} from {key} db')
            with self._connect(key) as conn:
                self._ensure_table(conn, type)
                return conn.execute(
                    f'SELECT * FROM {type.__name__} WHERE time >= ? AND time < ? ORDER BY time',
                    [start, end]
                ).fetchall()
        rows = await asyncio.get_running_loop().run_in_executor(None, inner)
        for row in rows:
            yield type(*row)

    async def store_time_series_and_span(
        self, key: Key, type: Type[Any], items: List[Any], start: int, end: int
    ) -> None:
        if len(items) > 0:
            if start > items[0].time:
                raise ValueError(f'Span start {start} bigger than first item time {items[0].time}')
            if end <= items[-1].time:
                raise ValueError(
                    f'Span end {end} smaller than or equal to last item time '
                    f'{items[-1].time}'
                )

        def inner() -> None:
            _log.info(
                f'storing {len(items)} {type.__name__}(s) between {strfspan(start, end)} to {key} '
                'db'
            )
            span_table_name = f'{type.__name__}{Span.__name__}'
            with self._connect(key) as conn:
                self._ensure_table(conn, type)
                self._ensure_table(conn, Span, span_table_name)

                c = conn.cursor()
                if len(items) > 0:
                    try:
                        c.executemany(
                            f"INSERT INTO {type.__name__} "
                            f"VALUES ({', '.join(['?'] * len(get_type_hints(type)))})", items
                        )
                    except sqlite3.IntegrityError as err:
                        # TODO: Can we relax this constraint?
                        _log.error(f'{err} {key}')
                        raise
                c.execute(f'INSERT INTO {span_table_name} VALUES (?, ?)', [start, end])
                conn.commit()

        await asyncio.get_running_loop().run_in_executor(None, inner)

    async def get(self, key: Key, type_: Type[T]) -> Tuple[Optional[T], Optional[int]]:
        def inner() -> Tuple[Optional[T], Optional[int]]:
            _log.info(f'getting value of type {get_name(type_)} from {key} db')
            with self._connect(key) as conn:
                self._ensure_table(conn, Bag)
                row = conn.execute(
                    f'SELECT * FROM {Bag.__name__} WHERE key=?', [get_name(type_)]
                ).fetchone()
                if row:
                    return _load_type_from_raw(type_, json.loads(row[1])), row[2]
                else:
                    return None, None

        return await asyncio.get_running_loop().run_in_executor(None, inner)

    async def set(self, key: Key, type_: Type[T], item: T) -> None:
        def inner() -> None:
            _log.info(f'setting value of type {get_name(type_)} to {key} db')
            with self._connect(key) as conn:
                self._ensure_table(conn, Bag)
                conn.execute(
                    f'INSERT OR REPLACE INTO {Bag.__name__} VALUES (?, ?, ?)',
                    [get_name(type_), json.dumps(item), time_ms()]
                )
                conn.commit()

        await asyncio.get_running_loop().run_in_executor(None, inner)

    def _connect(self, key: Key) -> ContextManager[sqlite3.Connection]:
        name = self._normalize_key(key)
        name = str(home_path('data') / f'v{self._version}_{name}.db')
        _log.debug(f'opening {name}')
        return closing(sqlite3.connect(name, detect_types=sqlite3.PARSE_DECLTYPES))

    def _ensure_table(
        self, conn: sqlite3.Connection, type_: Type[Any], name: Optional[str] = None
    ) -> None:
        if name is None:
            name = type_.__name__
        tables = self._tables[conn]
        if name not in tables:
            c = conn.cursor()
            _create_table(c, type_, name)
            conn.commit()
            tables.add(name)

    def _normalize_key(self, key: Key) -> str:
        key_type = type(key)
        if key_type is str:
            return cast(str, key)
        elif key_type is tuple:
            return '_'.join(map(str, key))
        else:
            raise NotImplementedError()


def _create_table(c: sqlite3.Cursor, type_: Type[Any], name: str) -> None:
    annotations = get_type_hints(type_)
    col_names = list(annotations.keys())
    col_types = [_type_to_sql_type(t) for t in annotations.values()]

    # Create table.
    cols = []
    for col_name, col_type in zip(col_names, col_types):
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
    # TODO: Use typing instead based on NewType()?
    VIEW_COL_NAMES = ['time', 'start', 'end']
    if any(n for n in col_names if n in VIEW_COL_NAMES):
        view_cols = []
        for col in col_names:
            if col in VIEW_COL_NAMES:
                view_cols.append(
                    f"strftime('%Y-%m-%d %H:%M:%S', {col} / 1000, 'unixepoch') AS {col}"
                )
            else:
                view_cols.append(col)

        c.execute(
            f'CREATE VIEW IF NOT EXISTS {name}View AS '
            f'SELECT {", ".join(view_cols)} FROM {name}'
        )


def _type_to_sql_type(type_: Type[Primitive]) -> str:
    if type_ is int:
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


def _load_type_from_raw(type_: Type[Any], value: Any) -> Any:
    # Needs to be a list because type_ can be non-hashable for lookup in a set.
    if type_ in [bool, int, float, str, Decimal]:
        return value

    origin = get_origin(type_) or type_
    if origin is list:
        sub_type = get_args(type_)[0]
        for i, sub_value in enumerate(value):
            value[i] = _load_type_from_raw(sub_type, sub_value)
        return value
    elif origin is dict:
        sub_type = get_args(type_)[1]
        for key, sub_value in value.items():
            value[key] = _load_type_from_raw(sub_type, sub_value)
        return value
    elif isnamedtuple(type_):
        values = []
        annotations = get_type_hints(type_)
        for i, (name, sub_type) in enumerate(annotations.items()):
            sub_value = value[i]
            values.append(_load_type_from_raw(sub_type, sub_value))
        return type_(*values)


class Bag:
    key: str
    value: str
    time: int

    @staticmethod
    def meta() -> Dict[str, str]:
        return {
            'key': 'unique',
        }


class Span:
    start: int
    end: int

    @staticmethod
    def meta() -> Dict[str, str]:
        return {
            'start': 'unique',
            'end': 'unique',
        }
