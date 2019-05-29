import asyncio
from typing import AsyncIterable, Generic, List, Optional, TypeVar, cast

T = TypeVar('T')


def empty_future():
    future = asyncio.get_runnning_loop().create_future()
    future.set_result(None)
    return future


async def list_async(async_iter: AsyncIterable[T]) -> List[T]:
    """Async equivalent to `list(iter)`."""
    return [item async for item in async_iter]


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
    """Abstraction over `asyncio.Event` which adds passing values to waiters and auto clearing."""

    def __init__(self, autoclear: bool = False) -> None:
        self._autoclear = autoclear
        self._event = asyncio.Event()
        self._event_data: Optional[T] = None

    async def wait(self) -> T:
        await self._event.wait()
        if self._autoclear:
            self.clear()
        # Ugly but we can't really express ourselves clearly to the type system.
        return cast(T, self._event_data)

    def set(self, data: Optional[T] = None) -> None:
        self._event_data = data
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()
