import asyncio
import logging
import sqlite3
from collections import defaultdict
from contextlib import closing
from decimal import Decimal
# TODO: mypy fails to recognise stdlib attributes get_args, get_origin. remove ignore when fixed
from typing import (  # type: ignore
    Any,
    AsyncIterable,
    ContextManager,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints
)

import juno.json as json
from juno.time import strfspan, time_ms
from juno.utils import home_path

from .storage import Storage

_log = logging.getLogger(__name__)

# Version should be incremented every time a storage schema changes.
_VERSION = 29

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
    def __init__(self) -> None:
        self._tables: Dict[Any, Set[str]] = defaultdict(set)

    async def stream_time_series_spans(self, key: Key, type: Type[T], start: int,
                                       end: int) -> AsyncIterable[Tuple[int, int]]:
        def inner() -> Iterable[Tuple[int, int]]:
            _log.info(
                f'streaming {type.__name__} span(s) between {strfspan(start, end)} from {key} db'
            )
            with self._connect(key) as db:
                span_table_name = f'{type.__name__}{Span.__name__}'
                self._ensure_table(db, Span, span_table_name)
                cursor = db.execute(
                    f'SELECT * FROM {span_table_name} WHERE start < ? AND end > ? ORDER BY start',
                    [end, start]
                )
                rows = cursor.fetchmany()
                return ((max(s, start), min(e, end)) for s, e in rows)

        for span in await asyncio.get_running_loop().run_in_executor(None, inner):
            yield span

    async def stream_time_series(self, key: Key, type: Type[T], start: int,
                                 end: int) -> AsyncIterable[T]:
        def inner() -> Iterable[T]:
            _log.info(f'streaming {type.__name__}(s) between {strfspan(start, end)} from {key} db')
            with self._connect(key) as db:
                self._ensure_table(db, type)
                cursor = db.execute(
                    f'SELECT * FROM {type.__name__} WHERE time >= ? AND time < ? ORDER BY time',
                    [start, end]
                )
                rows = cursor.fetchmany()
                for row in rows:
                    yield type(*row)

        for item in await asyncio.get_running_loop().run_in_executor(None, inner):
            yield item

    async def store_time_series_and_span(
        self, key: Key, type: Type[Any], items: List[Any], start: int, end: int
    ) -> None:
        def inner() -> None:
            if len(items) > 0:
                if start > items[0].time:
                    raise ValueError(
                        f'Span start {start} bigger than first item time {items[0].time}'
                    )
                if end <= items[-1].time:
                    raise ValueError(
                        f'Span end {end} smaller than or equal to last item time '
                        f'{items[-1].time}'
                    )

            _log.info(
                f'storing {len(items)} {type.__name__}(s) between {strfspan(start, end)} to {key} '
                'db'
            )
            with self._connect(key) as db:
                if len(items) > 0:
                    self._ensure_table(db, type)
                    try:
                        db.executemany(
                            f"INSERT INTO {type.__name__} "
                            f"VALUES ({', '.join(['?'] * len(get_type_hints(type)))})", items
                        )
                    except sqlite3.IntegrityError as err:
                        # TODO: Can we relax this constraint?
                        _log.error(f'{err} {key}')
                        raise

                span_table_name = f'{type.__name__}{Span.__name__}'
                self._ensure_table(db, Span, span_table_name)
                db.execute(f'INSERT INTO {span_table_name} VALUES (?, ?)', [start, end])
                db.commit()

        return await asyncio.get_running_loop().run_in_executor(None, inner)

    async def get(self, key: Key, type_: Type[T]) -> Tuple[Optional[T], Optional[int]]:
        def inner() -> Tuple[Optional[T], Optional[int]]:
            _log.info(f'getting value of type {type_.__name__} from {key} db')
            with self._connect(key) as db:
                self._ensure_table(db, Bag)
                cursor = db.execute(
                    f'SELECT * FROM {Bag.__name__} WHERE key=?', [type_.__name__]
                )
                row = cursor.fetchone()
                cursor.close()
                if row:
                    return _load_type_from_string(type_, json.loads(row[1])), row[2]
                else:
                    return None, None

        return await asyncio.get_running_loop().run_in_executor(None, inner)

    async def set(self, key: Key, type_: Type[T], item: T) -> None:
        def inner() -> None:
            _log.info(f'setting value of type {type_.__name__} to {key} db')
            with self._connect(key) as db:
                self._ensure_table(db, Bag)
                db.execute(
                    f'INSERT OR REPLACE INTO {Bag.__name__} VALUES (?, ?, ?)',
                    [type_.__name__, json.dumps(item), time_ms()]
                )
                db.commit()

        return await asyncio.get_running_loop().run_in_executor(None, inner)

    async def get_map(self, key: Key,
                      type_: Type[T]) -> Tuple[Optional[Dict[str, T]], Optional[int]]:
        def inner() -> Tuple[Optional[Dict[str, T]], Optional[int]]:
            _log.info(f'getting map of items of type {type_.__name__} from {key} db')
            with self._connect(key) as db:
                self._ensure_table(db, Bag)
                cursor = db.execute(
                    f'SELECT * FROM {Bag.__name__} WHERE key=?', ['map_' + type_.__name__]
                )
                row = cursor.fetchone()
                cursor.close()
                if row:
                    return {
                        k: _load_type_from_string(type_, v)
                        for k, v in json.loads(row[1]).items()
                    }, row[2]
                else:
                    return None, None

        return await asyncio.get_running_loop().run_in_executor(None, inner)

    # TODO: Generic type
    async def set_map(self, key: Key, type_: Type[T], items: Dict[str, T]) -> None:
        def inner() -> None:
            _log.info(f'setting map of {len(items)} items of type  {type_.__name__} to {key} db')
            with self._connect(key) as db:
                self._ensure_table(db, Bag)
                db.execute(
                    f'INSERT OR REPLACE INTO {Bag.__name__} VALUES (?, ?, ?)',
                    ['map_' + type_.__name__, json.dumps(items),
                        time_ms()]
                )
                db.commit()
        return await asyncio.get_running_loop().run_in_executor(None, inner)

    def _connect(self, key: Key) -> ContextManager[sqlite3.Connection]:
        # Normalize key.
        key_type = type(key)
        if key_type is str:
            normalized_key = cast(str, key)
        elif key_type is tuple:
            normalized_key = '_'.join(map(str, key))
        else:
            raise NotImplementedError()

        name, is_uri = self._get_db_name(normalized_key)
        _log.debug(f'opening {name}')
        return closing(sqlite3.connect(name, uri=is_uri, detect_types=sqlite3.PARSE_DECLTYPES))

    def _get_db_name(self, key: str) -> Tuple[str, bool]:
        return str(home_path('data') / f'v{_VERSION}_{key}.db'), False

    def _ensure_table(self, db: Any, type_: Type[Any], name: Optional[str] = None) -> None:
        if name is None:
            name = type_.__name__
        tables = self._tables[db]
        if name not in tables:
            _create_table(db, type_, name)
            db.commit()
            tables.add(name)

    def _normalize_key(self, key: Key) -> str:
        key_type = type(key)
        if key_type is str:
            return cast(str, key)
        elif key_type is tuple:
            return '_'.join(map(str, key))
        else:
            raise NotImplementedError()


def _create_table(db: sqlite3.Connection, type_: Type[Any], name: str) -> None:
    annotations = get_type_hints(type_)
    col_names = list(annotations.keys())
    col_types = [_type_to_sql_type(t) for t in annotations.values()]

    # Create table.
    cols = []
    for col_name, col_type in zip(col_names, col_types):
        cols.append(f'{col_name} {col_type} NOT NULL')
    db.execute(f'CREATE TABLE IF NOT EXISTS {name} ({", ".join(cols)})')

    # Add indices.
    meta_getter = getattr(type_, 'meta', None)
    meta = meta_getter() if meta_getter else None
    if meta:
        for n, c in meta.items():
            if c == 'index':
                db.execute(f'CREATE INDEX IF NOT EXISTS {name}Index ON {name}({n})')
            elif c == 'unique':
                db.execute(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS {name}UniqueIndex ON {name}({n})'
                )
            else:
                raise NotImplementedError()

    # Create debug views.
    # TODO: Use typing instead based on NewType()?
    VIEW_COL_NAMES = ['time', 'start', 'end']
    if any((n for n in col_names if n in VIEW_COL_NAMES)):
        view_cols = []
        for col in col_names:
            if col in VIEW_COL_NAMES:
                view_cols.append(
                    f"strftime('%Y-%m-%d %H:%M:%S', {col} / 1000, 'unixepoch') AS {col}"
                )
            else:
                view_cols.append(col)

        db.execute(
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


def _isnamedtuple(type_: Type[Any]) -> bool:
    return issubclass(type_, tuple) and bool(getattr(type_, '_fields', False))


def _load_type_from_string(type_: Type[Any], values: Union[Dict[str, Any], tuple]) -> Any:
    annotations = get_type_hints(type_)
    for i, (key, attr_type) in enumerate(annotations.items()):
        index = i if _isnamedtuple(type_) else key
        if get_origin(attr_type) is dict:
            sub_type = get_args(attr_type)[1]
            sub = values[index]  # type: ignore
            for dk, dv in sub.items():
                sub[dk] = _load_type_from_string(sub_type, dv)
        elif _isnamedtuple(attr_type):
            # Materialize it.
            values[index] = _load_type_from_string(attr_type, values[index])  # type: ignore
    return type_(*values) if _isnamedtuple(type_) else type_(**values)


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
