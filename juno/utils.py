import asyncio
import contextlib
import inspect
import itertools
import logging
import random
import traceback
from collections.abc import MutableMapping, MutableSequence
from copy import deepcopy
from dataclasses import asdict, is_dataclass, make_dataclass
from os import path
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterator, Optional, Sequence, Tuple, Type, TypeVar, get_type_hints

import aiolimiter

from juno import json
from juno.typing import ExcType, ExcValue, Traceback, isnamedtuple

T = TypeVar('T')

_log = logging.getLogger(__name__)


def _asdict(a: Any) -> dict:
    if isinstance(a, dict):
        return a
    if is_dataclass(a):
        return asdict(a)
    if isnamedtuple(a):
        return a._asdict()
    return a.__dict__


def construct(type_: Type[T], *args, **kwargs) -> T:
    type_hints = get_type_hints(type_)
    final_kwargs = {}
    for d in itertools.chain(map(_asdict, args), [kwargs]):
        final_kwargs.update({k: v for k, v in d.items() if k in type_hints.keys()})
    return type_(**final_kwargs)  # type: ignore


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


def extract_public(obj: Any, exclude: Sequence[str] = []) -> Any:
    """Turns all public fields and properties of an object into typed output. Non-recursive.
    """

    type_ = type(obj)

    # TODO: We can cache the generated type based on input type.
    attrs = []
    vals = []

    # Fields.
    fields = (
        (n, v) for (n, v) in get_type_hints(type_).items()
        if not n.startswith('_') and n not in exclude
    )
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

    output_type = make_dataclass(type_.__name__, attrs)
    return output_type(*vals)


def _isprop(v: object) -> bool:
    return isinstance(v, property)


def exc_traceback(exc: Exception) -> str:
    return ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def map_concrete_module_types(
    module: ModuleType, abstract: Optional[Type[Any]] = None
) -> Dict[str, Type[Any]]:
    return {n.lower(): t for n, t in inspect.getmembers(
        module,
        lambda c: (
            inspect.isclass(c)
            and not inspect.isabstract(c)
            and (True if abstract is None else issubclass(c, abstract))
        )
    )}


# Cannot use typevar T in place of Any here. Triggers: "Only concrete class can be given where type
# is expected".
# Ref: https://github.com/python/mypy/issues/5374
def list_concretes_from_module(module: ModuleType, abstract: Type[Any]) -> list[Type[Any]]:
    return [t for _n, t in inspect.getmembers(
        module,
        lambda m: inspect.isclass(m) and not inspect.isabstract(m) and issubclass(m, abstract)
    )]


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


class AbstractAsyncContextManager(contextlib.AbstractAsyncContextManager):
    async def __aexit__(self, exc_type: ExcType, exc_value: ExcValue, tb: Traceback) -> None:
        pass
