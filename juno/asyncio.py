import asyncio
import logging
import os
import signal
import traceback
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Coroutine,
    Generic,
    Iterable,
    Optional,
    TypeVar,
    cast,
)

_log = logging.getLogger(__name__)

T = TypeVar("T")
U = TypeVar("U")


def resolved_future(result: T) -> asyncio.Future:
    future = asyncio.get_running_loop().create_future()
    future.set_result(result)
    return future


async def resolved_stream(*results: T) -> AsyncIterable[T]:
    for result in results:
        yield result


async def stream_with_timeout(
    async_iter: AsyncIterable[T], timeout: Optional[float]
) -> AsyncIterable[T]:
    iterator = aiter(async_iter)
    try:
        while True:
            yield await asyncio.wait_for(anext(iterator), timeout=timeout)
    except StopAsyncIteration:
        pass


async def first_async(async_iter: AsyncIterable[T]) -> T:
    async for item in async_iter:
        await aclose(async_iter)
        return item
    raise ValueError("First not found. No elements in sequence")


# Ref: https://stackoverflow.com/a/50903757/1466456
async def merge_async(*async_iters: AsyncIterable[T]) -> AsyncIterable[T]:
    iter_next: dict[AsyncIterator[T], Optional[asyncio.Future]] = {
        it.__aiter__(): None for it in async_iters
    }
    while iter_next:
        for it, it_next in iter_next.items():
            if it_next is None:
                fut = asyncio.ensure_future(it.__anext__())
                fut._orig_iter = it  # type: ignore
                iter_next[it] = fut
        done, _ = await asyncio.wait(
            iter_next.values(), return_when=asyncio.FIRST_COMPLETED  # type: ignore
        )
        for fut in done:  # type: ignore
            iter_next[fut._orig_iter] = None  # type: ignore
            try:
                ret = fut.result()
            except StopAsyncIteration:
                del iter_next[fut._orig_iter]  # type: ignore
                continue
            yield ret


async def gather_dict(tasks: dict[T, Awaitable[U]]) -> dict[T, U]:
    async def mark(key: T, coro: Awaitable[U]) -> tuple[T, U]:
        return key, await coro

    return {
        key: result
        for key, result in await asyncio.gather(*(mark(key, coro) for key, coro in tasks.items()))
    }


async def cancel(*tasks: Optional[asyncio.Task]) -> None:
    await asyncio.gather(*(_cancel(t) for t in tasks if t))


async def _cancel(task: asyncio.Task) -> None:
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        qualname = task.get_coro().__class__.__qualname__
        _log.info(f"{qualname} task cancelled")


def create_task_sigint_on_exception(coro: Coroutine) -> asyncio.Task:
    """Creates a new task.
    Sends a SIGINT on unhandled exception.
    """

    def callback(task: asyncio.Task) -> None:
        task_name = task.get_coro().__class__.__qualname__
        if not task.cancelled() and (exc := task.exception()):
            msg = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            _log.error(f"unhandled exception in {task_name} task ({msg})")
            os.kill(os.getpid(), signal.SIGINT)

    child_task = asyncio.create_task(coro)
    child_task.add_done_callback(callback)
    return child_task


def create_task_cancel_owner_on_exception(coro: Coroutine) -> asyncio.Task:
    """Creates a new task.
    Cancels the parent task in case the child task raises an unhandled exception.
    """
    parent_task = asyncio.current_task()

    def callback(task):
        task_name = task.get_coro().__qualname__
        if not task.cancelled() and (exc := task.exception()):
            if exc := task.exception():
                msg = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                _log.error(f"unhandled exception in {task_name} task ({msg})")
                # parent_task.set_exception(exc)  # Not allowed for a task.
                parent_task.cancel()

    child_task = asyncio.create_task(coro)
    child_task.add_done_callback(callback)
    return child_task


async def stream_queue(
    queue: asyncio.Queue, timeout: Optional[float] = None, raise_on_exc: bool = False
) -> AsyncIterable[Any]:
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=timeout)
        if raise_on_exc and isinstance(item, Exception):
            raise item
        yield item
        queue.task_done()


async def process_task_on_queue(queue: asyncio.Queue, coro: Awaitable[T]) -> T:
    # Useful for awaiting for a task but shielding it from cancellation.
    task = asyncio.create_task(_schedule_queue_task_done(queue, coro))
    queue.put_nowait(task)
    queue.get_nowait()
    await queue.join()
    return task.result()


async def _schedule_queue_task_done(queue: asyncio.Queue, coro: Awaitable[T]) -> T:
    try:
        return await coro
    finally:
        queue.task_done()


class Barrier:
    def __init__(self, count: int) -> None:
        if count < 0:
            raise ValueError("Count cannot be negative")

        self._count = count
        self._event = asyncio.Event()
        self.clear()

    @property
    def locked(self) -> bool:
        return self._remaining_count > 0

    def clear(self) -> None:
        self._event.clear()
        self._remaining_count = self._count
        if not self.locked:
            self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    def release(self) -> None:
        if self._remaining_count > 0:
            self._remaining_count -= 1
        else:
            raise ValueError("Barrier already unlocked")

        if not self.locked:
            self._event.set()


@dataclass
class _Slot:
    locked: bool = True
    cleared: asyncio.Event = field(default_factory=asyncio.Event)


class SlotBarrier(Generic[T]):
    def __init__(self, slots: Iterable[T]) -> None:
        self._slots = {s: _Slot() for s in set(slots)}
        self._event = asyncio.Event()
        self.clear()

    @property
    def locked(self) -> bool:
        return any(s.locked for s in self._slots.values())

    def slot_locked(self, slot: T) -> bool:
        return self._slots[slot].locked

    def clear(self) -> None:
        self._event.clear()
        for slot in self._slots.values():
            slot.locked = True
            slot.cleared.set()
        self._update_locked()

    async def wait(self) -> None:
        await self._event.wait()

    def release(self, slot: T) -> None:
        slot_ = self._slots.get(slot)

        if slot_ is None:
            raise ValueError(f"Slot {slot} does not exist")

        if slot_.locked:
            slot_.locked = False
        else:
            raise ValueError(f"Slot {slot} already released")

        self._update_locked()

    def add(self, slot: T) -> None:
        assert slot not in self._slots
        self._slots[slot] = _Slot()
        self._update_locked()

    def delete(self, slot: T) -> None:
        del self._slots[slot]
        self._update_locked()

    def _update_locked(self) -> None:
        if not self.locked:
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


async def aclose(async_iterable: Any) -> None:
    if isinstance(async_iterable, AsyncGenerator):
        await async_iterable.aclose()
