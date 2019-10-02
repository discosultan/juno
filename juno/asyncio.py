import asyncio
import inspect
import logging
import traceback
from typing import Any, AsyncIterable, Awaitable, Generic, List, Optional, TypeVar, Union, cast

T = TypeVar('T')


def empty_future() -> asyncio.Future:
    future = asyncio.get_running_loop().create_future()
    future.set_result(None)
    return future


async def list_async(async_iter: AsyncIterable[T]) -> List[T]:
    """Async equivalent to `list(iter)`."""
    return [item async for item in async_iter]


async def concat_async(*args: Union[T, AsyncIterable[T]]) -> AsyncIterable[T]:
    for arg in args:
        if hasattr(arg, '__aiter__'):
            async for val in arg:  # type: ignore
                yield val
        else:
            yield arg  # type: ignore


def cancelable(coro: Awaitable[Any]) -> Awaitable[Any]:
    frame = inspect.stack()[1]
    module = inspect.getmodule(frame[0])

    async def inner() -> Any:
        try:
            return await coro
        except asyncio.CancelledError:
            log = logging.getLogger(module.__name__)
            log.info(f'{coro.__qualname__} task cancelled')
        except Exception as exc:
            log = logging.getLogger(module.__name__)
            msg = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            log.error(f'unhandled exception in {coro.__qualname__} task ({msg})')
            raise

    return inner()


async def cancel(*tasks: Optional[asyncio.Task]) -> None:
    material_tasks = [task for task in tasks if task and not task.done()]
    for task in material_tasks:
        task.cancel()
    await asyncio.gather(*material_tasks)


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
