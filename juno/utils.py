import asyncio
import base64
import inspect
import itertools
import logging
import random
import traceback
from os import path
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, Optional, TypeVar
from uuid import uuid4

import aiolimiter

from juno import json

T = TypeVar("T")

_log = logging.getLogger(__name__)


def key(*items: Any) -> str:
    return "_".join(map(str, items))


def generate_random_words(length: Optional[int] = None) -> Iterator[str]:
    if length is not None and (length < 2 or 14 < length):
        raise ValueError("Length must be between 2 and 14")

    from juno.data.words import WORDS

    words = itertools.cycle(sorted(iter(WORDS), key=lambda _: random.random()))
    return filter(lambda w: len(w) == length, words) if length else words


def unpack_assets(symbol: str) -> tuple[str, str]:
    index_of_separator = symbol.find("-")
    return symbol[:index_of_separator], symbol[index_of_separator + 1 :]


def unpack_base_asset(symbol: str) -> str:
    index_of_separator = symbol.find("-")
    return symbol[:index_of_separator]


def unpack_quote_asset(symbol: str) -> str:
    index_of_separator = symbol.find("-")
    return symbol[index_of_separator + 1 :]


def home_path(*args: str) -> Path:
    path = Path(Path.home(), ".juno").joinpath(*args)
    path.mkdir(parents=True, exist_ok=True)
    return path


def full_path(root: str, rel_path: str) -> str:
    return path.join(path.dirname(root), *filter(None, rel_path.split("/")))


def load_json_file(root: str, rel_path: str) -> Any:
    with open(full_path(root, rel_path)) as f:
        return json.load(f)


def exc_traceback(exc: Exception) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def map_concrete_module_types(
    module: ModuleType, abstract: Optional[type[Any]] = None
) -> dict[str, type[Any]]:
    return {
        n.lower(): t
        for n, t in inspect.getmembers(
            module,
            lambda c: (
                inspect.isclass(c)
                and not inspect.isabstract(c)
                and (True if abstract is None else issubclass(c, abstract))
            ),
        )
    }


# Cannot use typevar T in place of Any here. Triggers: "Only concrete class can be given where type
# is expected".
# Ref: https://github.com/python/mypy/issues/5374
def list_concretes_from_module(module: ModuleType, abstract: type[Any]) -> list[type[Any]]:
    return [
        t
        for _n, t in inspect.getmembers(
            module,
            lambda m: inspect.isclass(m) and not inspect.isabstract(m) and issubclass(m, abstract),
        )
    ]


def get_module_type(module: ModuleType, name: str) -> type[Any]:
    name_lower = name.lower()
    found_members = inspect.getmembers(
        module, lambda obj: inspect.isclass(obj) and obj.__name__.lower() == name_lower
    )
    if len(found_members) == 0:
        raise ValueError(f'Type named "{name}" not found in module "{module.__name__}".')
    if len(found_members) > 1:
        raise ValueError(f'Found more than one type named "{name}" in module "{module.__name__}".')
    return found_members[0][1]


def short_uuid4() -> str:
    uuid_bytes = uuid4().bytes
    uuid_bytes_b64 = base64.urlsafe_b64encode(uuid_bytes)
    uuid_b64 = uuid_bytes_b64.decode("ascii")
    return uuid_b64[:-2]  # Remove '==' suffix from the end.


class AsyncLimiter(aiolimiter.AsyncLimiter):
    # Overrides the original implementation by adding logging when rate limiting.
    # https://github.com/mjpieters/aiolimiter/blob/master/src/aiolimiter/leakybucket.py
    async def acquire(self, amount: float = 1) -> None:
        if amount > self.max_rate:
            raise ValueError("Can't acquire more than the maximum capacity")

        loop = asyncio.get_event_loop()
        task = asyncio.current_task(loop)
        assert task is not None
        while not self.has_capacity(amount):
            waiting_time = 1 / self._rate_per_sec * amount
            _log.info(
                f"rate limiter {self.max_rate}/{self.time_period} reached; waiting up to "
                f"{waiting_time}s before retrying"
            )
            fut = loop.create_future()
            self._waiters[task] = fut
            try:
                await asyncio.wait_for(asyncio.shield(fut), waiting_time)
            except asyncio.TimeoutError:
                pass
            fut.cancel()
        self._waiters.pop(task, None)

        self._level += amount
