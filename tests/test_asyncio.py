import asyncio

import pytest
from asyncstdlib.itertools import pairwise as pairwise_async

from juno.asyncio import (
    Barrier,
    Event,
    SlotBarrier,
    cancel,
    dict_async,
    first_async,
    map_async,
    merge_async,
)


async def test_dict_async() -> None:
    async def gen():
        for k, v in zip(["a", "b", "c"], [0, 1, 2]):
            yield k, v

    assert await dict_async(gen()) == {
        "a": 0,
        "b": 1,
        "c": 2,
    }


async def test_first_async() -> None:
    async def gen():
        yield 1
        yield 2

    assert await first_async(gen()) == 1


async def test_merge_async() -> None:
    signal1 = asyncio.Event()
    signal2 = asyncio.Event()

    async def gen1():
        yield 0
        signal2.set()
        await signal1.wait()
        yield 2
        signal2.set()

    async def gen2():
        await signal2.wait()
        signal2.clear()
        yield 1
        signal1.set()
        await signal2.wait()
        yield 3

    counter = 0
    async for val in merge_async(gen1(), gen2()):
        assert val == counter
        counter += 1
    assert counter == 4


async def test_map_async() -> None:
    async def gen():
        yield 1
        yield 2

    expected_values = [2, 4]
    async for x in map_async(lambda x: x * 2, gen()):
        assert x == expected_values.pop(0)


@pytest.mark.parametrize(
    "input_,expected_output",
    [
        ([], []),
        ([1], []),
        ([1, 2], [(1, 2)]),
        ([1, 2, 3], [(1, 2), (2, 3)]),
    ],
)
async def test_pairwise_async(input_: list[int], expected_output: list[tuple[int, int]]) -> None:
    async def gen():
        for val in input_:
            yield val

    async for x in pairwise_async(gen()):
        assert x == expected_output.pop(0)


async def test_barrier() -> None:
    barrier = Barrier(2)
    wait_task = asyncio.create_task(barrier.wait())
    assert barrier.locked
    assert not wait_task.done()

    barrier.release()
    await asyncio.sleep(0)
    assert barrier.locked
    assert not wait_task.done()

    barrier.release()
    await asyncio.sleep(0)
    assert not barrier.locked
    assert wait_task.done()

    barrier.clear()
    wait_task = asyncio.create_task(barrier.wait())
    assert barrier.locked
    assert not wait_task.done()

    barrier.release()
    await asyncio.sleep(0)
    assert barrier.locked
    assert not wait_task.done()

    barrier.release()
    await asyncio.sleep(0)
    assert not barrier.locked
    assert wait_task.done()


async def test_barrier_exceptions() -> None:
    barrier = Barrier(1)

    with pytest.raises(ValueError):
        barrier.release()
        barrier.release()

    assert not barrier.locked


async def test_slot_barrier() -> None:
    barrier = SlotBarrier(["a", "b"])
    wait_task = asyncio.create_task(barrier.wait())
    assert barrier.locked
    assert not wait_task.done()

    barrier.release("a")
    await asyncio.sleep(0)
    assert barrier.locked
    assert not wait_task.done()

    barrier.release("b")
    await asyncio.sleep(0)
    assert not barrier.locked
    assert wait_task.done()

    barrier.clear()
    wait_task = asyncio.create_task(barrier.wait())
    assert barrier.locked
    assert not wait_task.done()

    barrier.release("a")
    await asyncio.sleep(0)
    assert barrier.locked
    assert not wait_task.done()

    barrier.release("b")
    await asyncio.sleep(0)
    assert not barrier.locked
    assert wait_task.done()


async def test_slot_barrier_exceptions() -> None:
    barrier = SlotBarrier(["a"])

    with pytest.raises(ValueError):
        barrier.release("b")

    with pytest.raises(ValueError):
        barrier.release("a")
        barrier.release("a")

    assert not barrier.locked


async def test_slot_barrier_add_delete() -> None:
    barrier = SlotBarrier(["a"])
    assert barrier.locked

    barrier.add("b")
    barrier.release("a")
    assert barrier.locked

    barrier.delete("b")
    assert not barrier.locked


async def test_cancel() -> None:
    done_task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(0))
    await done_task
    none_task = None
    pending_task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(1))

    await cancel(done_task, none_task, pending_task)


async def test_empty_barrier() -> None:
    barrier = Barrier(0)
    await asyncio.wait_for(barrier.wait(), timeout=0.001)


async def test_event_multiple_receivers() -> None:
    event: Event[str] = Event()

    t1 = event.wait()
    t2 = event.wait()

    event.set("value")

    r1, r2 = await asyncio.gather(t1, t2)

    assert r1 == "value"
    assert r2 == "value"
    assert event.is_set()


async def test_event_autoclear() -> None:
    event: Event[str] = Event(autoclear=True)

    t = event.wait()

    event.set("value")

    r = await t

    assert r == "value"
    assert not event.is_set()
