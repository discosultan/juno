import asyncio
import pytest

from juno.utils import generate_missing_spans, merge_adjacent_spans, Barrier, Event


@pytest.mark.parametrize('input,expected_output', [
    ([(0, 1), (1, 2), (3, 4), (4, 5)], [(0, 2), (3, 5)])
])
def test_merge_adjacent_spans(input, expected_output):
    output = list(merge_adjacent_spans(input))
    assert output == expected_output


@pytest.mark.parametrize('start,end,spans,expected_output', [
    (0, 5, [(1, 2), (3, 4)], [(0, 1), (2, 3), (4, 5)]),
    (2, 5, [(1, 3), (4, 6)], [(3, 4)])
])
def test_generate_missing_spans(start, end, spans, expected_output):
    output = list(generate_missing_spans(start, end, spans))
    assert output == expected_output


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


async def test_event(loop):
    event = Event()

    t1 = event.wait()
    t2 = event.wait()

    event.set('value')

    r1, r2 = await asyncio.gather(t1, t2)

    assert r1 == 'value'
    assert r2 == 'value'
