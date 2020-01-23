import operator

import pytest

from juno import Trend, math
from juno.strategies import Meta, Persistence, Strategy


def test_strategy_meta():
    strategy = DummyStrategy()

    strategy.validate(5, 15)
    with pytest.raises(ValueError):
        strategy.validate(-5, 15)
        strategy.validate(5, 25)
        strategy.validate(11, 9)


class DummyStrategy(Strategy):

    meta = Meta(
        constraints={
            ('foo', 'bar'): math.Pair(math.Int(0, 15), operator.lt, math.Int(10, 20)),
        }
    )

    def tick(self, candle):
        pass


def test_persistence_level_0_allow_initial_trend():
    persistence = Persistence(level=0, allow_initial=True)
    assert persistence.update(Trend.UP) == (True, True)
    assert persistence.update(Trend.UP) == (True, False)
    assert persistence.update(Trend.DOWN) == (True, True)
    assert persistence.update(None) == (False, True)
    assert persistence.update(Trend.UP) == (True, True)


def test_persistence_level_0_disallow_initial_trend():
    persistence = Persistence(level=0, allow_initial=False)
    assert persistence.update(Trend.UP) == (False, False)
    assert persistence.update(Trend.UP) == (False, False)


def test_persistence_level_0_disallow_initial_trend_starting_with_unknown_does_not_skip_initial():
    persistence = Persistence(level=0, allow_initial=False)
    assert persistence.update(None) == (False, False)
    assert persistence.update(Trend.UP) == (True, True)


def test_persistence_level_1_allow_initial_trend():
    persistence = Persistence(level=1, allow_initial=True)
    assert persistence.update(Trend.UP) == (False, False)
    assert persistence.update(Trend.UP) == (True, True)
    assert persistence.update(Trend.UP) == (True, False)
    assert persistence.update(Trend.DOWN) == (True, False)
    assert persistence.update(Trend.DOWN) == (True, True)
    assert persistence.update(None) == (True, False)
    assert persistence.update(None) == (False, True)


def test_persistence_level_1_disallow_initial_trend():
    persistence = Persistence(level=1, allow_initial=False)
    assert persistence.update(Trend.UP) == (False, False)
    assert persistence.update(Trend.UP) == (False, False)
    assert persistence.update(Trend.UP) == (False, False)


def test_persistence_level_1_disallow_initial_trend_starting_with_unknown_does_not_skip_initial():
    persistence = Persistence(level=1, allow_initial=False)
    assert persistence.update(None) == (False, False)
    assert persistence.update(Trend.UP) == (False, False)
    assert persistence.update(Trend.UP) == (True, True)


def test_persistence_level_1_disallow_initial_trend_starting_with_up_does_not_skip_initial():
    persistence = Persistence(level=1, allow_initial=False)
    assert persistence.update(Trend.UP) == (False, False)
    assert persistence.update(Trend.DOWN) == (False, False)
    assert persistence.update(Trend.DOWN) == (True, True)


def test_persistence_level_1_allow_initial_trend_change_resets_age():
    persistence = Persistence(level=1, allow_initial=True)
    assert persistence.update(Trend.UP) == (False, False)
    assert persistence.update(Trend.UP) == (True, True)
    assert persistence.update(Trend.DOWN) == (True, False)
    assert persistence.update(Trend.UP) == (True, False)
    assert persistence.update(Trend.DOWN) == (True, False)
    assert persistence.update(Trend.DOWN) == (True, True)
