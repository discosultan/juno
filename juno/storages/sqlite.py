import asyncio
import logging
import sqlite3
from collections import defaultdict
from contextlib import closing
from decimal import Decimal
from typing import (
    Any,
    AsyncIterable,
    ContextManager,
    NamedTuple,
    Optional,
    TypeVar,
    Union,
    get_type_hints,
)

from juno import Interval, Timestamp, Timestamp_, json, serialization
from juno.itertools import generate_missing_spans, merge_adjacent_spans
from juno.path import home_path

from .storage import Storage

_log = logging.getLogger(__name__)

# Version should be incremented every time a storage schema changes.
_VERSION = "v52"

T = TypeVar("T")

Primitive = Union[bool, int, float, Decimal, str]


def _serialize_decimal(d: Decimal) -> bytes:
    return str(d).encode("ascii")


def _deserialize_decimal(s: bytes) -> Decimal:
    return Decimal(s.decode("ascii"))


sqlite3.register_adapter(Decimal, _serialize_decimal)
sqlite3.register_converter("DECIMAL", _deserialize_decimal)

sqlite3.register_adapter(bool, int)
sqlite3.register_converter("BOOLEAN", lambda v: bool(int(v)))


class SQLite(Storage):
    def __init__(self, version: Optional[str] = None) -> None:
        self._version = _VERSION if version is None else version
        self._tables: dict[Any, set[str]] = defaultdict(set)
        _log.info(f"sqlite version: {sqlite3.sqlite_version}; schema version: {self._version}")

    async def stream_time_series_spans(
        self, shard: str, key: str, start: Timestamp = 0, end: Timestamp = Timestamp_.MAX_TIME
    ) -> AsyncIterable[tuple[Timestamp, Timestamp]]:
        def inner() -> list[tuple[Timestamp, Timestamp]]:
            _log.info(
                f"streaming span(s) between {Timestamp_.format_span(start, end)} from shard "
                f"{shard} {key}"
            )
            with self._connect(shard) as conn:
                span_key = f"{key}_{_SPAN_KEY}"
                self._ensure_table(conn, span_key, Span)
                return conn.execute(
                    f"SELECT * FROM {span_key} WHERE start < ? AND end > ? ORDER BY start",
                    [end, start],
                ).fetchall()

        rows = await asyncio.get_running_loop().run_in_executor(None, inner)
        for span_start, span_end in merge_adjacent_spans(rows):
            yield max(span_start, start), min(span_end, end)

    async def stream_time_series(
        self,
        shard: str,
        key: str,
        type_: type[T],
        start: Timestamp = 0,
        end: Timestamp = Timestamp_.MAX_TIME,
    ) -> AsyncIterable[T]:
        def inner() -> list[T]:
            _log.info(
                f"streaming items between {Timestamp_.format_span(start, end)} from shard {shard} "
                f"{key}"
            )
            with self._connect(shard) as conn:
                self._ensure_table(conn, key, type_)
                return conn.execute(
                    f"SELECT * FROM {key} WHERE time >= ? AND time < ? ORDER BY time",
                    [start, end],
                ).fetchall()

        rows = await asyncio.get_running_loop().run_in_executor(None, inner)
        for row in rows:
            yield serialization.raw.deserialize(row, type_)

    async def store_time_series_and_span(
        self, shard: str, key: str, items: list[Any], start: Timestamp, end: Timestamp
    ) -> None:
        # Even if items list is empty, we still want to store a span for the period!
        if len(items) > 0:
            type_ = type(items[0])
            if start > items[0].time:
                raise ValueError(f"Span start {start} bigger than first item time {items[0].time}")
            if end <= items[-1].time:
                raise ValueError(
                    f"Span end {end} smaller than or equal to last item time {items[-1].time}"
                )

        def inner() -> None:
            span_key = f"{key}_{_SPAN_KEY}"
            with self._connect(shard) as conn:
                self._ensure_table(conn, span_key, Span)
                if len(items) > 0:
                    self._ensure_table(conn, key, type_)

                c = conn.cursor()
                existing_spans = c.execute(
                    f"SELECT * FROM {span_key} WHERE start < ? AND end > ? ORDER BY start",
                    [end, start],
                ).fetchall()
                merged_existing_spans = merge_adjacent_spans(existing_spans)
                missing_spans = list(generate_missing_spans(start, end, merged_existing_spans))
                if len(missing_spans) == 0:
                    return
                missing_item_spans = (
                    [items]
                    if len(existing_spans) == 0
                    else [
                        [i for i in items if i.time >= s and i.time < e] for s, e in missing_spans
                    ]
                )
                for (mstart, mend), mitems in zip(missing_spans, missing_item_spans):
                    _log.info(
                        f"inserting {len(mitems)} item(s) between "
                        f"{Timestamp_.format_span(mstart, mend)} to shard {shard} {key}"
                    )
                    if len(mitems) > 0:
                        try:
                            c.executemany(
                                f"INSERT INTO {key} "
                                f'VALUES ({", ".join(["?"] * len(get_type_hints(type_)))})',
                                mitems,
                            )
                        except sqlite3.IntegrityError as err:
                            _log.error(f"{err} {shard} {key}")
                            raise
                    c.execute(f"INSERT INTO {span_key} VALUES (?, ?)", [mstart, mend])
                conn.commit()

        await asyncio.get_running_loop().run_in_executor(None, inner)

    async def get(self, shard: str, key: str, type_: type[T]) -> Optional[T]:
        def inner() -> Optional[T]:
            _log.info(f"getting {key} from shard {shard}")
            with self._connect(shard) as conn:
                self._ensure_table(conn, _KEY_VALUE_PAIR_KEY, KeyValuePair)
                row = conn.execute(
                    f"SELECT * FROM {_KEY_VALUE_PAIR_KEY} WHERE key=? LIMIT 1", [key]
                ).fetchone()
                return serialization.raw.deserialize(json.loads(row[1]), type_) if row else None

        return await asyncio.get_running_loop().run_in_executor(None, inner)

    async def set(self, shard: str, key: str, item: T) -> None:
        def inner() -> None:
            _log.info(f"setting {key} to shard {shard}")
            with self._connect(shard) as conn:
                self._ensure_table(conn, _KEY_VALUE_PAIR_KEY, KeyValuePair)
                conn.execute(
                    f"INSERT OR REPLACE INTO {_KEY_VALUE_PAIR_KEY} VALUES (?, ?)",
                    [key, json.dumps(serialization.raw.serialize(item))],
                )
                conn.commit()

        await asyncio.get_running_loop().run_in_executor(None, inner)

    def _connect(self, shard: str) -> ContextManager[sqlite3.Connection]:
        path = str(home_path("data") / f"{self._version}_{shard}.db")
        _log.debug(f"opening shard {path}")
        return closing(sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES))

    def _ensure_table(self, conn: sqlite3.Connection, name: str, type_: type[Any]) -> None:
        tables = self._tables[conn]
        if name not in tables:
            c = conn.cursor()
            _create_table(c, type_, name)
            conn.commit()
            tables.add(name)


def _create_table(c: sqlite3.Cursor, type_: type[Any], name: str) -> None:
    type_hints = get_type_hints(type_)
    col_types = [(k, _type_to_sql_type(v)) for k, v in type_hints.items()]

    # Create table.
    cols = []
    for col_name, col_type in col_types:
        cols.append(f"{col_name} {col_type} NOT NULL")
    c.execute(f'CREATE TABLE IF NOT EXISTS {name} ({", ".join(cols)})')

    # Add indices.
    meta_getter = getattr(type_, "meta", None)
    meta = meta_getter() if meta_getter else None
    if meta:
        for cname, ctype in meta.items():
            if ctype == "index":
                c.execute(f"CREATE INDEX IF NOT EXISTS {name}Index ON {name}({cname})")
            elif ctype == "unique":
                c.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {name}UniqueIndex ON {name}({cname})"
                )
            else:
                raise NotImplementedError()

    # Create debug views.
    view_cols = []
    create_view = False
    for col_name, type_ in type_hints.items():
        if type_ is Timestamp:
            view_cols.append(
                f"strftime('%Y-%m-%d %H:%M:%S', {col_name} / 1000, 'unixepoch') AS "
                f"{col_name}_representation"
            )
            create_view = True
        view_cols.append(col_name)
    if create_view:
        c.execute(
            f"CREATE VIEW IF NOT EXISTS {name}View AS "
            f'SELECT {", ".join(view_cols)} FROM {name}'
        )


def _type_to_sql_type(type_: type[Primitive]) -> str:
    if type_ in [Interval, Timestamp, int]:
        return "INTEGER"
    if type_ is float:
        return "REAL"
    if type_ is Decimal:
        return "DECIMAL"
    if type_ is str:
        return "TEXT"
    if type_ is bool:
        return "BOOLEAN"
    raise NotImplementedError(f"Missing conversion for type {type_}")


class KeyValuePair(NamedTuple):
    key: str
    value: str

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            "key": "unique",
        }


class Span(NamedTuple):
    start: Timestamp
    end: Timestamp

    @staticmethod
    def meta() -> dict[str, str]:
        return {
            "start": "unique",
            "end": "unique",
        }


_KEY_VALUE_PAIR_KEY = KeyValuePair.__name__.lower()
_SPAN_KEY = Span.__name__.lower()
