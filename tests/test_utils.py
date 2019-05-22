import asyncio
import sys
from abc import ABC, abstractmethod
from statistics import mean
from typing import List

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


def test_page():
    pages = list(utils.page(start=0, end=5, interval=1, limit=2))
    assert len(pages) == 3
    assert pages[0][0] == 0
    assert pages[0][1] == 2
    assert pages[1][0] == 2
    assert pages[1][1] == 4
    assert pages[2][0] == 4
    assert pages[2][1] == 5


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


def test_unpack_symbol():
    assert utils.unpack_symbol('eth-btc') == ('eth', 'btc')


def test_flatten():
    expected_output = [35, 53, 525, 6743, 64, 63, 743, 754, 757]
    output = list(utils.flatten([35, 53, [525, 6743], 64, 63, [743, 754, 757]]))
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


def test_circular_buffer():
    buffer = utils.CircularBuffer(size=2, default=0)

    buffer.push(2)
    buffer.push(4)

    assert len(buffer) == 2
    assert sum(buffer) == 6
    assert mean(buffer) == 3
    assert min(buffer) == 2
    assert max(buffer) == 4

    buffer.push(6)

    assert len(buffer) == 2
    assert sum(buffer) == 10
    assert mean(buffer) == 5
    assert min(buffer) == 4
    assert max(buffer) == 6


def test_map_dependencies():
    dep_map = utils.map_dependencies(
        [Baz],
        [sys.modules[__name__]],
        lambda a, c: [c[0]])

    assert dep_map == {
        Baz: [Foo],
        Foo: [Bar],
        Bar: []
    }


def test_list_deps_in_init_order():
    dep_map = {
        Baz: [Foo],
        Foo: [Bar],
        Bar: []
    }

    assert utils.list_deps_in_init_order(dep_map) == [
        [Bar],
        [Baz]
    ]


class Foo(ABC):

    @abstractmethod
    def dummy(self):
        pass


class Bar(Foo):

    def dummy(self):
        pass


class Baz:

    def __init__(self, foo: List[Foo], baz: int) -> None:
        pass
