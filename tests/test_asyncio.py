import asyncio

from juno.asyncio import (
    Barrier, Event, chain_async, enumerate_async, list_async, merge_async, resolved_stream
)


async def test_chain_async():
    async def gen():
        yield 1
        yield 2

    target = chain_async(resolved_stream(0), gen())

    assert await target.__anext__() == 0
    assert await target.__anext__() == 1
    assert await target.__anext__() == 2
    await target.aclose()


async def test_enumerate_async():
    async def gen():
        yield 'a'
        yield 'b'

    target = enumerate_async(gen(), start=1)

    assert await target.__anext__() == (1, 'a')
    assert await target.__anext__() == (2, 'b')
    await target.aclose()


async def test_list_async():
    async def gen():
        for i in range(3):
            yield i

    assert await list_async(gen()) == [0, 1, 2]


async def test_merge_async():
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
        yield 1
        signal1.set()
        await signal2.wait()
        yield 3

    counter = 0
    async for val in merge_async(gen1(), gen2()):
        assert val == counter
        counter += 1


async def test_barrier():
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


async def test_empty_barrier():
    barrier = Barrier(0)
    await asyncio.wait_for(barrier.wait(), timeout=0.001)


async def test_event_multiple_receivers():
    event = Event()

    t1 = event.wait()
    t2 = event.wait()

    event.set('value')

    r1, r2 = await asyncio.gather(t1, t2)

    assert r1 == 'value'
    assert r2 == 'value'
    assert event.is_set()


async def test_event_autoclear():
    event = Event(autoclear=True)

    t = event.wait()

    event.set('value')

    r = await t

    assert r == 'value'
    assert not event.is_set()
