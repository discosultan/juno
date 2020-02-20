import asyncio
import inspect
import itertools
import logging
import math
import random
import traceback
from collections import defaultdict
from collections.abc import MutableMapping, MutableSequence
from copy import deepcopy
from os import path
from pathlib import Path
from types import ModuleType
from typing import (
    Any, Awaitable, Callable, Dict, Generic, Iterable, Iterator, List, NamedTuple, Optional, Tuple,
    Type, TypeVar, Union, get_type_hints
)

import aiolimiter

from juno import json

T = TypeVar('T')

_log = logging.getLogger(__name__)


def merge_adjacent_spans(spans: Iterable[Tuple[int, int]]) -> Iterable[Tuple[int, int]]:
    merged_start, merged_end = None, None

    for start, end in spans:
        if merged_start is None:
            merged_start, merged_end = start, end
        elif merged_end == start:
            merged_end = end
        else:
            yield merged_start, merged_end
            merged_start, merged_end = start, end

    if merged_start is not None:
        yield merged_start, merged_end  # type: ignore


def generate_missing_spans(start: int, end: int,
                           existing_spans: Iterable[Tuple[int, int]]) -> Iterable[Tuple[int, int]]:
    # Initially assume entire span missing.
    missing_start, missing_end = start, end

    # Spans are ordered by start_date. Spans do not overlap with each other.
    for existing_start, existing_end in existing_spans:
        if existing_start > missing_start:
            yield missing_start, existing_start
        missing_start = existing_end

    if missing_start < missing_end:
        yield missing_start, missing_end


def page(start: int, end: int, interval: int, limit: int) -> Iterable[Tuple[int, int]]:
    total_size = (end - start) / interval
    max_count = limit * interval
    page_size = math.ceil(total_size / limit)
    for i in range(0, page_size):
        page_start = start + i * max_count
        page_end = min(page_start + max_count, end)
        yield page_start, page_end


# TODO: Remove if not used.
def replace_secrets(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Do not mutate source obj.
    obj = deepcopy(obj)

    # Replace secret values.
    stack = [obj]
    while stack:
        item = stack.pop()
        if isinstance(item, MutableMapping):  # Json object.
            it = item.items()
        elif isinstance(item, MutableSequence):  # Json array.
            it = enumerate(item)
        else:  # Scalar.
            continue

        for k, v in it:
            if 'secret' in k and isinstance(v, str):
                item[k] = '********'
            else:
                stack.append(v)

    return obj


# Ref: https://stackoverflow.com/a/38397347/1466456
def recursive_iter(obj: Any, keys: Tuple[Any, ...] = ()) -> Iterable[Tuple[Tuple[Any, ...], Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from recursive_iter(v, keys + (k, ))
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            yield from recursive_iter(item, keys + (idx, ))
    else:
        yield keys, obj


_words = None


def generate_random_words(length: Optional[int] = None) -> Iterator[str]:
    global _words

    if length is not None and (length < 2 or 14 < length):
        raise ValueError('Length must be between 2 and 14')

    if not _words:
        _words = load_json_file(__file__, './data/words.json')
        _words = itertools.cycle(sorted(iter(_words), key=lambda _: random.random()))

    return filter(lambda w: len(w) == length, _words) if length else _words


def unpack_symbol(symbol: str) -> Tuple[str, str]:
    index_of_separator = symbol.find('-')
    return symbol[:index_of_separator], symbol[index_of_separator + 1:]


def home_path(*args: str) -> Path:
    path = Path(Path.home(), '.juno').joinpath(*args)
    path.mkdir(parents=True, exist_ok=True)
    return path


def full_path(root: str, rel_path: str) -> str:
    return path.join(path.dirname(root), *filter(None, rel_path.split('/')))


def load_json_file(root: str, rel_path: str) -> Any:
    with open(full_path(root, rel_path)) as f:
        return json.load(f)


# TODO: Use `recursive_iter` instead?
# Ref: https://stackoverflow.com/a/10632356/1466456
def flatten(items: Iterable[Union[T, List[T]]]) -> Iterable[T]:
    for item in items:
        if isinstance(item, (list, tuple)):
            for subitem in item:
                yield subitem
        else:
            yield item


def map_module_types(module: ModuleType) -> Dict[str, type]:
    return {n.lower(): t for n, t in inspect.getmembers(module, inspect.isclass)}


def list_concretes_from_module(module: ModuleType, abstract: Type[Any]) -> List[Type[Any]]:
    return [t for _n, t in inspect.getmembers(
        module,
        lambda m: inspect.isclass(m) and not inspect.isabstract(m) and issubclass(m, abstract)
    )]


# TODO: Generalize typing to lists.
# Ref: https://stackoverflow.com/a/312464/1466456
def chunks(l: str, n: int) -> Iterable[str]:
    """Yield successive n-sized chunks from l."""
    length = len(l)
    if length <= n:
        yield l
    else:
        for i in range(0, length, n):
            yield l[i:i + n]


def tonamedtuple(obj: Any) -> Any:
    type_ = type(obj)
    # if type_ in [int, float, bool, str, Decimal, tuple, list, dict]:
    #     return obj

    # TODO: We can cache the named tuple based on input type.
    attrs = []
    vals = []

    # Fields.
    fields = [(n, v) for (n, v) in get_type_hints(type_).items() if not n.startswith('_')]
    for name, field_type in fields:
        attrs.append((name, field_type))
        vals.append(getattr(obj, name))

    # Properties.
    props = [(n, v) for (n, v) in inspect.getmembers(type_, _isprop) if not n.startswith('_')]
    # Inspect orders members alphabetically. We want to preserve source ordering.
    props.sort(key=lambda prop: prop[1].fget.__code__.co_firstlineno)
    for name, prop in props:
        prop_type = get_type_hints(prop.fget)['return']
        attrs.append((name, prop_type))
        vals.append(prop.fget(obj))

    # TODO: NamedTuples are not meant to be created dynamically.
    namedtuple = NamedTuple(type_.__name__, attrs)  # type: ignore

    return namedtuple(*vals)


def _isprop(v: object) -> bool:
    return isinstance(v, property)


def get_module_type(module: ModuleType, name: str) -> Type[Any]:
    name_lower = name.lower()
    found_members = inspect.getmembers(
        module,
        lambda obj: inspect.isclass(obj) and obj.__name__.lower() == name_lower
    )
    if len(found_members) == 0:
        raise ValueError(f'Type named "{name}" not found in module "{module.__name__}".')
    if len(found_members) > 1:
        raise ValueError(f'Found more than one type named "{name}" in module "{module.__name__}".')
    return found_members[0][1]


def exc_traceback(exc: Exception) -> str:
    return ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))


class CircularBuffer(Generic[T]):
    def __init__(self, size: int, default: T) -> None:
        if size < 0:
            raise ValueError('Size must be positive')

        self._values = [default] * size
        self._index = 0

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[T]:
        return iter(self._values)

    def push(self, value: T) -> None:
        if len(self._values) == 0:
            raise ValueError('Unable to push to buffer of size 0')

        self._values[self._index] = value
        self._index = (self._index + 1) % len(self._values)


class EventEmitter:
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[..., Awaitable[None]]]] = defaultdict(list)

    def on(self, event: str) -> Callable[[Callable[..., Awaitable[None]]], None]:
        def _on(func: Callable[..., Awaitable[None]]) -> None:
            self._handlers[event].append(func)

        return _on

    async def emit(self, event: str, *args: Any) -> List[Any]:
        return await asyncio.gather(
            *(x(*args) for x in self._handlers[event]), return_exceptions=True
        )


class AsyncLimiter(aiolimiter.AsyncLimiter):
    # Overrides the original implementation by adding logging when rate limiting.
    # https://github.com/mjpieters/aiolimiter/blob/master/src/aiolimiter/leakybucket.py
    async def acquire(self, amount: float = 1) -> None:
        if amount > self.max_rate:
            raise ValueError("Can't acquire more than the maximum capacity")

        loop = aiolimiter.compat.get_running_loop()
        task = aiolimiter.compat.current_task(loop)
        assert task is not None
        while not self.has_capacity(amount):
            waiting_time = 1 / self._rate_per_sec * amount
            _log.info(
                f'rate limiter {self.max_rate}/{self.time_period} reached; waiting up to '
                f'{waiting_time}s before retrying'
            )
            fut = loop.create_future()
            self._waiters[task] = fut
            try:
                await asyncio.wait_for(asyncio.shield(fut), waiting_time, loop=loop)
            except asyncio.TimeoutError:
                pass
            fut.cancel()
        self._waiters.pop(task, None)

        self._level += amount
