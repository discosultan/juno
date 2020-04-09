import operator

import pytest

from juno import Advice, math, strategies


def test_strategy_meta():
    strategy = DummyStrategy()

    strategy.validate(5, 15)
    with pytest.raises(ValueError):
        strategy.validate(-5, 15)
        strategy.validate(5, 25)
        strategy.validate(11, 9)


class DummyStrategy(strategies.Strategy):
    @staticmethod
    def meta() -> strategies.Meta:
        return strategies.Meta(
            constraints={
                ('foo', 'bar'): math.Pair(math.Int(0, 15), operator.lt, math.Int(10, 20)),
            }
        )

    def tick(self, candle):
        pass


def test_ignore_mid_trend_disabled() -> None:
    target = strategies.IgnoreNotMatureAndMidTrend(maturity=0, ignore_mid_trend=False)
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_ignore_mid_trend_enabled() -> None:
    target = strategies.IgnoreNotMatureAndMidTrend(maturity=0, ignore_mid_trend=True)
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_ignore_mid_trend_starting_with_none_does_not_skip_first(
) -> None:
    target = strategies.IgnoreNotMatureAndMidTrend(maturity=0, ignore_mid_trend=True)
    assert target.update(Advice.NONE) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG


def test_ignore_not_mature(
) -> None:
    target = strategies.IgnoreNotMatureAndMidTrend(maturity=1, ignore_mid_trend=False)
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_ignore_not_mature_and_mid_trend() -> None:
    target = strategies.IgnoreNotMatureAndMidTrend(maturity=2, ignore_mid_trend=True)

    assert target.update(Advice.SHORT) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG


def test_persistence_level_0() -> None:
    target = strategies.Persistence(level=0)
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_persistence_level_1() -> None:
    target = strategies.Persistence(level=1)
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_changed_disabled() -> None:
    target = strategies.Changed(enabled=False)
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.NONE) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_changed_enabled() -> None:
    target = strategies.Changed(enabled=True)
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.NONE) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.SHORT
