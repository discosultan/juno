import asyncio
import inspect
import logging
import traceback
from typing import Any, AsyncIterable, Awaitable, Generic, List, Optional, Tuple, TypeVar, cast

T = TypeVar('T')


def resolved_future(result: T) -> asyncio.Future[T]:
    future = asyncio.get_running_loop().create_future()
    future.set_result(result)
    return future


async def resolved_stream(*results: T) -> AsyncIterable[T]:
    for result in results:
        yield result


async def chain_async(*async_iters: AsyncIterable[T]) -> AsyncIterable[T]:
    for async_iter in async_iters:
        async for val in async_iter:
            yield val


async def enumerate_async(iterable: AsyncIterable[T],
                          start: int = 0, step: int = 1) -> AsyncIterable[Tuple[int, T]]:
    i = start
    async for item in iterable:
        yield i, item
        i += step


async def list_async(async_iter: AsyncIterable[T]) -> List[T]:
    """Async equivalent to `list(iter)`."""
    return [item async for item in async_iter]


async def merge_async(*async_iters: AsyncIterable[T]) -> AsyncIterable[T]:
    # TODO: Implement
    yield


def cancelable(coro: Awaitable[Any]) -> Awaitable[Any]:
    frame = inspect.stack()[1]
    module = inspect.getmodule(frame[0])

    async def inner() -> Any:
        assert module
        try:
            return await coro
        except asyncio.CancelledError:
            log = logging.getLogger(module.__name__)
            # Available on coroutine.
            qualname = getattr(coro, '__qualname__', None)
            # Other awaitables.
            qualname = type(coro).__qualname__ if qualname is None else qualname
            log.info(f'{qualname} task cancelled')
        except Exception as exc:
            log = logging.getLogger(module.__name__)
            msg = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            log.error(f'unhandled exception in {coro.__qualname__} task ({msg})')  # type: ignore
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
    """Abstraction over `asyncio.Event` which adds additional capabilities:

    - passing data through set
    - autoclear after wait
    - timeout on wait"""
    def __init__(self, autoclear: bool = False) -> None:
        self._autoclear = autoclear
        self._event = asyncio.Event()
        self._event_data: Optional[T] = None

    async def wait(self, timeout: Optional[float] = None) -> T:
        if timeout is not None:
            await asyncio.wait_for(self._event.wait(), timeout)
        else:
            await self._event.wait()
        if self._autoclear:
            self.clear()
        # Ugly but we can't really express ourselves clearly to the type system.
        return cast(T, self._event_data)

    async def stream(self, timeout: Optional[float] = None) -> AsyncIterable[T]:
        while True:
            yield await self.wait(timeout)

    def set(self, data: Optional[T] = None) -> None:
        self._event_data = data
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()
