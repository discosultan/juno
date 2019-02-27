import asyncio

import pytest

from juno import utils


@pytest.mark.parametrize('input,expected_output', [
    ([(0, 1), (1, 2), (3, 4), (4, 5)], [(0, 2), (3, 5)])
])
def test_merge_adjacent_spans(input, expected_output):
    output = list(utils.merge_adjacent_spans(input))
    assert output == expected_output


@pytest.mark.parametrize('start,end,spans,expected_output', [
    (0, 5, [(1, 2), (3, 4)], [(0, 1), (2, 3), (4, 5)]),
    (2, 5, [(1, 3), (4, 6)], [(3, 4)])
])
def test_generate_missing_spans(start, end, spans, expected_output):
    output = list(utils.generate_missing_spans(start, end, spans))
    assert output == expected_output


def test_recursive_iter():
    input = {
        'aa': 'ab',
        'ba': {
            'ca': 'cb'
        },
        'da': [
            {'ea': 'eb'}
        ]
    }
    expected_output = [
        (('aa',), 'ab'),
        (('ba', 'ca'), 'cb'),
        (('da', 0, 'ea'), 'eb')
    ]
    output = list(utils.recursive_iter(input))
    assert output == expected_output


async def test_barrier(loop):
    barrier = utils.Barrier(2)
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
    barrier = utils.Barrier(0)
    await asyncio.wait_for(barrier.wait(), timeout=0.001)


async def test_event(loop):
    event = utils.Event()

    t1 = event.wait()
    t2 = event.wait()

    event.set('value')

    r1, r2 = await asyncio.gather(t1, t2)

    assert r1 == 'value'
    assert r2 == 'value'


def test_trend_without_age_threshold():
    trend = utils.Trend(0)
    # Ensure advice skipped when starting in the middle of a trend.
    assert trend.update(1) == 0
    assert trend.update(1) == 0
    # Ensure advice signaled on trend change.
    assert trend.update(-1) == -1
    assert trend.update(1) == 1
    # Ensure advice not signaled twice for a trend.
    assert trend.update(1) == 0
    # Ensure when getting no trend direction and then receiving old
    # direction again, advice is not signaled again.
    assert trend.update(0) == 0
    assert trend.update(1) == 0
    # Ensure starting with no trend does not skip the initial trend.
    trend = utils.Trend(0)
    assert trend.update(0) == 0
    assert trend.update(1) == 1


def test_trend_with_age_threshold():
    # Ensure advice is skipped when starting in the middle of a trend.
    trend = utils.Trend(1)
    assert trend.update(1) == 0
    assert trend.update(1) == 0
    # Ensure advice signaled after age threshold.
    assert trend.update(-1) == 0
    assert trend.update(-1) == -1
    # Ensure moving out of trend and back to it does not re-signal the advice.
    assert trend.update(0) == 0
    assert trend.update(-1) == 0
    assert trend.update(-1) == 0
    # Ensure starting with a trend that hasn't passed age threshold does not skip the initial trend
    # for opposite dir.
    trend = utils.Trend(1)
    assert trend.update(1) == 0
    assert trend.update(-1) == 0
    assert trend.update(-1) == -1
    # Ensure starting with no trend does not skip the initial trend.
    trend = utils.Trend(1)
    assert trend.update(0) == 0
    assert trend.update(1) == 0
    assert trend.update(1) == 1
    # Ensure that even if trend dir changes, if it has not passed the age threshold, going back to
    # previous dir does not re-signal the advice.
    assert trend.update(-1) == 0
    assert trend.update(1) == 0
    assert trend.update(1) == 0
    # Ensure that even if trend is updated without dir, the age is still incremented for previous
    # trend.
    assert trend.update(-1) == 0
    assert trend.update(0) == 0
    assert trend.update(-1) == -1
    # Ensure that even if trend is updated without dir and the age is incremented for previous
    # trend above its threshold, going back to the dir signals advice.
    assert trend.update(1) == 0
    assert trend.update(0) == 0
    assert trend.update(0) == 0
    assert trend.update(1) == 1
