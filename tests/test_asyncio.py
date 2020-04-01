import asyncio
import weakref

from juno.asyncio import (
    Barrier, Event, cancel, chain_async, enumerate_async, first_async, list_async, merge_async,
    resolved_stream, zip_async
)


async def test_chain_async() -> None:
    async def gen():
        yield 1
        yield 2

    expected_output = [0, 1, 2]

    target = chain_async(resolved_stream(0), gen())

    async for result in target:
        assert result == expected_output.pop(0)


async def test_enumerate_async() -> None:
    async def gen():
        yield 'a'
        yield 'b'

    expected_output = [
        (1, 'a'),
        (2, 'b'),
    ]

    target = enumerate_async(gen(), start=1)

    async for result in target:
        assert result == expected_output.pop(0)


async def test_list_async() -> None:
    async def gen():
        for i in range(3):
            yield i

    assert await list_async(gen()) == [0, 1, 2]


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


async def test_zip_async() -> None:
    async def gen1():
        yield 0
        yield 2

    async def gen2():
        yield 1
        yield 3

    counter = 0
    async for a, b in zip_async(gen1(), gen2()):
        assert a == counter
        assert b == counter + 1
        counter += 2
    assert counter == 4


async def test_barrier() -> None:
    barrier = Barrier(2)
    event = asyncio.Event()

    async def process_event():
        await barrier.wait()
        event.set()

    process_event_task = asyncio.create_task(process_event())

    barrier.release()
    await asyncio.sleep(0)
    assert not event.is_set()

    barrier.release()
    await asyncio.sleep(0)
    assert event.is_set()

    assert process_event_task.done()


async def test_cancel() -> None:
    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task
    none_task = None
    pending_task = asyncio.create_task(asyncio.sleep(1))
    weakref_task = weakref.ref(asyncio.create_task(asyncio.sleep(1)))

    await cancel(done_task, none_task, pending_task, weakref_task)


async def test_empty_barrier() -> None:
    barrier = Barrier(0)
    await asyncio.wait_for(barrier.wait(), timeout=0.001)


async def test_event_multiple_receivers() -> None:
    event: Event[str] = Event()

    t1 = event.wait()
    t2 = event.wait()

    event.set('value')

    r1, r2 = await asyncio.gather(t1, t2)

    assert r1 == 'value'
    assert r2 == 'value'
    assert event.is_set()


async def test_event_autoclear() -> None:
    event: Event[str] = Event(autoclear=True)

    t = event.wait()

    event.set('value')

    r = await t

    assert r == 'value'
    assert not event.is_set()
