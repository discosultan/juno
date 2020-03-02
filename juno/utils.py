import asyncio
import inspect
import itertools
import logging
import random
import traceback
from collections.abc import MutableMapping, MutableSequence
from copy import deepcopy
from os import path
from pathlib import Path
from typing import (
    Any, Dict, Generic, Iterator, NamedTuple, Optional, Tuple, TypeVar, get_type_hints
)

import aiolimiter

from juno import json
from juno.config import to_config
from juno.typing import isnamedtuple

T = TypeVar('T')

_log = logging.getLogger(__name__)


def key(*items: Any) -> str:
    return '_'.join(map(str, items))


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


_words = None


def generate_random_words(length: Optional[int] = None) -> Iterator[str]:
    global _words

    if length is not None and (length < 2 or 14 < length):
        raise ValueError('Length must be between 2 and 14')

    if not _words:
        _words = load_json_file(__file__, './data/words.json')
        _words = itertools.cycle(sorted(iter(_words), key=lambda _: random.random()))

    return filter(lambda w: len(w) == length, _words) if length else _words


def format_as_config(obj: Any):
    type_ = type(obj)
    if not isnamedtuple(type_):
        # Extracts only public fields and properties.
        obj = tonamedtuple(obj)
        type_ = type(obj)
    return json.dumps(to_config(obj, type_), indent=4)


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


def tonamedtuple(obj: Any) -> Any:
    """Turns all public fields and properties of an object into typed named tuple. Non-recursive.
    """

    type_ = type(obj)

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

    # TODO: mypy doesn't like when NamedTuples are created dynamically. It's okay for our use case
    # because we only use them like this for log output formatting.
    namedtuple = NamedTuple(type_.__name__, attrs)  # type: ignore

    return namedtuple(*vals)


def _isprop(v: object) -> bool:
    return isinstance(v, property)


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
