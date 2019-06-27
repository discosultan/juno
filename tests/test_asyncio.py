import asyncio

from juno.asyncio import Barrier, Event, concat_async, list_async


async def test_list_async(loop):

    async def gen():
        for i in range(3):
            yield i

    assert await list_async(gen()) == [0, 1, 2]


async def test_concat_async(loop):

    async def gen():
        yield 1
        yield 2

    counter = 0
    async for val in concat_async(0, gen()):
        assert val == counter
        counter += 1


async def test_barrier(loop):
    barrier = Barrier(2)
    event = asyncio.Event()

    async def process_event():
        await barrier.wait()
        event.set()

    _process_event_task = loop.create_task(process_event())

    barrier.release()
    await asyncio.sleep(0)
    assert not event.is_set()

    barrier.release()
    await asyncio.sleep(0)
    assert event.is_set()

    assert _process_event_task.done()


async def test_empty_barrier(loop):
    barrier = Barrier(0)
    await asyncio.wait_for(barrier.wait(), timeout=0.001)


async def test_event_multiple_receivers(loop):
    event = Event()

    t1 = event.wait()
    t2 = event.wait()

    event.set('value')

    r1, r2 = await asyncio.gather(t1, t2)

    assert r1 == 'value'
    assert r2 == 'value'
    assert event.is_set()


async def test_event_autoclear(loop):
    event = Event(autoclear=True)

    t = event.wait()

    event.set('value')

    r = await t

    assert r == 'value'
    assert not event.is_set()
