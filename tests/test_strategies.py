import operator

import pytest

from juno import Advice, math
from juno.strategies import Meta, Persistence, Strategy


def test_strategy_meta():
    strategy = DummyStrategy()

    strategy.validate(5, 15)
    with pytest.raises(ValueError):
        strategy.validate(-5, 15)
        strategy.validate(5, 25)
        strategy.validate(11, 9)


class DummyStrategy(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                ('foo', 'bar'): math.Pair(math.Int(0, 15), operator.lt, math.Int(10, 20)),
            }
        )

    def tick(self, candle):
        pass


def test_persistence_level_0_allow_initial_trend() -> None:
    persistence = Persistence(level=0, default=Advice.NONE, allow_initial=True)
    assert persistence.update(Advice.LONG) == (True, True)
    assert persistence.update(Advice.LONG) == (True, False)
    assert persistence.update(Advice.SHORT) == (True, True)
    assert persistence.update(Advice.NONE) == (False, True)
    assert persistence.update(Advice.LONG) == (True, True)


def test_persistence_level_0_disallow_initial_trend() -> None:
    persistence = Persistence(level=0, default=Advice.NONE, allow_initial=False)
    assert persistence.update(Advice.LONG) == (False, False)
    assert persistence.update(Advice.LONG) == (False, False)


def test_persistence_level_0_disallow_initial_trend_starting_with_unknown_does_not_skip_initial(
) -> None:
    persistence = Persistence(level=0, default=Advice.NONE, allow_initial=False)
    assert persistence.update(Advice.NONE) == (False, False)
    assert persistence.update(Advice.LONG) == (True, True)


def test_persistence_level_1_allow_initial_trend() -> None:
    persistence = Persistence(level=1, default=Advice.NONE, allow_initial=True)
    assert persistence.update(Advice.LONG) == (False, False)
    assert persistence.update(Advice.LONG) == (True, True)
    assert persistence.update(Advice.LONG) == (True, False)
    assert persistence.update(Advice.SHORT) == (True, False)
    assert persistence.update(Advice.SHORT) == (True, True)
    assert persistence.update(Advice.NONE) == (True, False)
    assert persistence.update(Advice.NONE) == (False, True)


def test_persistence_level_1_disallow_initial_trend() -> None:
    persistence = Persistence(level=1, default=Advice.NONE, allow_initial=False)
    assert persistence.update(Advice.LONG) == (False, False)
    assert persistence.update(Advice.LONG) == (False, False)
    assert persistence.update(Advice.LONG) == (False, False)


def test_persistence_level_1_disallow_initial_trend_starting_with_unknown_does_not_skip_initial(
) -> None:
    persistence = Persistence(level=1, default=Advice.NONE, allow_initial=False)
    assert persistence.update(Advice.NONE) == (False, False)
    assert persistence.update(Advice.LONG) == (False, False)
    assert persistence.update(Advice.LONG) == (True, True)


def test_persistence_level_1_disallow_initial_trend_starting_with_up_does_not_skip_initial(
) -> None:
    persistence = Persistence(level=1, default=Advice.NONE, allow_initial=False)
    assert persistence.update(Advice.LONG) == (False, False)
    assert persistence.update(Advice.SHORT) == (False, False)
    assert persistence.update(Advice.SHORT) == (True, True)


def test_persistence_level_1_allow_initial_trend_change_resets_age() -> None:
    persistence = Persistence(level=1, default=Advice.NONE, allow_initial=True)
    assert persistence.update(Advice.LONG) == (False, False)
    assert persistence.update(Advice.LONG) == (True, True)
    assert persistence.update(Advice.SHORT) == (True, False)
    assert persistence.update(Advice.LONG) == (True, False)
    assert persistence.update(Advice.SHORT) == (True, False)
    assert persistence.update(Advice.SHORT) == (True, True)
