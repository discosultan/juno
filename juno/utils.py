import asyncio
import math
import random
from collections import defaultdict
from typing import (Any, AsyncIterable, Awaitable, Callable, Dict, Generic, Iterable, Iterator,
                    List, Optional, Tuple, Type, TypeVar, cast)

import backoff

T = TypeVar('T')


async def list_async(async_iter: AsyncIterable[T]) -> List[T]:
    return [item async for item in async_iter]


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


# Ref: https://stackoverflow.com/a/38397347/1466456
def recursive_iter(obj: Any, keys: Tuple[Any, ...] = ()) -> Iterable[Tuple[Tuple[Any, ...], Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from recursive_iter(v, keys + (k,))
    elif any(isinstance(obj, t) for t in (list, tuple)):
        for idx, item in enumerate(obj):
            yield from recursive_iter(item, keys + (idx,))
    else:
        yield keys, obj


def retry_on(exception: Type[Exception],
             max_tries: Optional[int] = None) -> Callable[[Callable[..., Any]], Any]:
    return cast(Callable[[Callable[..., Any]], Any],
                backoff.on_exception(backoff.expo, exception, max_tries=max_tries))


def gen_random_names() -> Iterable[str]:
    random_words = [
        'custumal', 'nummary', 'bamboozlement', 'bider', 'ellipticity', 'unscribbled', 'dampishly',
        'insincerity', 'vaticide', 'qualifiedness', 'tolerableness', 'dolph', 'olethreutid',
        'tensileness', 'besetment', 'suspiciousness', 'santander', 'stately', 'albategnius',
        'repositories', 'delaine', 'surfaceless', 'prelusorily', 'loins', 'unneutralised',
        'dropsy', 'poet', 'remodeling', 'intracellularly', 'strengtheningly', 'organography',
        'romanticistic', 'exchangee', 'brawn', 'defilade', 'cowpox', 'serpent', 'arginine',
        'unbroached', 'phdre', 'trustbuster', 'souter', 'deiced', 'multifistulous', 'ruffian',
        'krupp', 'kerbaya', 'biddable', 'marcel', 'creneling', 'rev', 'untransposed', 'cordelle',
        'encopresis', 'glykopexic', 'superabsurd', 'sanaa', 'deign', 'sternwheeler', 'katrine',
        'afrasian', 'jeannette', 'seora', 'disrate', 'airdrie', 'regrow', 'endoperidium',
        'strophoid', 'direst', 'justificative', 'iyyar', 'puss', 'stipulation', 'subsonic',
        'hyman', 'unsour', 'popish', 'carrara', 'mtb', 'flashing', 'retotaled', 'remediably',
        'telophasic', 'safford', 'suboxide', 'matchbox', 'preextinguish', 'uncobbled', 'stalinsk',
        'bogarde', 'jerrid', 'recategorized', 'intercarotid', 'eurypterid', 'fluidics', 'charity',
        'underwork', 'skill', 'actionable', 'judith'
    ]
    return sorted(iter(random_words), key=lambda _: random.random())


# Implements a leaky bucket algorithm. Useful for rate limiting API calls.
# Implementation taken from: https://stackoverflow.com/a/45502319/1466456
class LeakyBucket:
    """A leaky bucket rate limiter.

    Allows up to rate / period acquisitions before blocking.

    Period is measured in seconds.
    """

    def __init__(self, rate: float, period: float) -> None:
        self._max_level = rate
        self._rate_per_sec = rate / period
        self._level = 0.0
        self._last_check = 0.0

    def _leak(self) -> None:
        """Drip out capacity from the bucket."""
        now = asyncio.get_running_loop().time()
        if self._level:
            # Drip out enough level for the elapsed time since we last checked.
            elapsed = now - self._last_check
            decrement = elapsed * self._rate_per_sec
            self._level = max(self._level - decrement, 0.0)
        self._last_check = now

    def has_capacity(self, amount: float = 1.0) -> bool:
        """Check if there is enough space remaining in the bucket."""
        self._leak()
        return self._level + amount <= self._max_level

    async def acquire(self, amount: float = 1.0) -> None:
        """Acquire space in the bucket.

        If the bucket is full, block until there is space.
        """
        if amount > self._max_level:
            raise ValueError("Can't acquire more than the bucket capacity")

        while not self.has_capacity(amount):
            # Wait for the next drip to have left the bucket.
            await asyncio.sleep(1.0 / self._rate_per_sec)

        self._level += amount


class Barrier:

    def __init__(self, count: int) -> None:
        if count < 0:
            raise ValueError('Count cannot be negative')

        self._remaining_count = count
        self._event = asyncio.Event()
        if count == 0:
            self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    def locked(self) -> bool:
        return self._remaining_count > 0

    def release(self) -> None:
        self._remaining_count = max(self._remaining_count - 1, 0)
        if not self.locked():
            self._event.set()


class Event(Generic[T]):

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._event_data: Optional[T] = None

    async def wait(self) -> T:
        await self._event.wait()
        assert self._event_data
        return self._event_data

    def set(self, data: T) -> None:
        self._event_data = data
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()


class Trend:

    def __init__(self, persistence: int) -> None:
        self.age = 0
        self.persistence = persistence
        self.last_dir = 0
        self.last_advice = 0
        self.initial_trend = True

    def update(self, direction: int) -> int:
        advice = 0
        if direction == 0:
            self.initial_trend = False
        else:
            if direction != self.last_dir:
                self.age = 0
                if self.last_dir != 0:
                    self.initial_trend = False
                self.last_dir = direction

            if not self.initial_trend and self.age == self.persistence:
                advice = 1 if direction == 1 else -1
                if advice is self.last_advice:
                    advice = 0
                else:
                    self.last_advice = advice

            self.age += 1
        return advice


class CircularBuffer(Generic[T]):

    def __init__(self, size: int, default: T) -> None:
        if size < 0:
            raise ValueError('Size must be positive')

        self.vals = [default] * size
        self.index = 0

    def __len__(self) -> int:
        return len(self.vals)

    def __iter__(self) -> Iterator[T]:
        return iter(self.vals)

    def push(self, val: T) -> None:
        if len(self.vals) == 0:
            raise ValueError('Unable to push to buffer of size 0')

        self.vals[self.index] = val
        self.index = (self.index + 1) % len(self.vals)


class EventEmitter:

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[..., Awaitable[None]]]] = defaultdict(list)

    def on(self, event: str) -> Callable[[Callable[..., Awaitable[None]]], None]:

        def _on(func: Callable[..., Awaitable[None]]) -> None:
            self._handlers[event].append(func)

        return _on

    async def emit(self, event: str, *args: Any) -> None:
        await asyncio.gather(*(x(*args) for x in self._handlers[event]))
