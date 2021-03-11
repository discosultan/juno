import operator

import pytest

from juno import Advice, Candle, strategies
from juno.constraints import Int, Pair
from juno.strategies import MidTrendPolicy, Strategy


class DummyStrategy(Strategy):
    @staticmethod
    def meta() -> Strategy.Meta:
        return Strategy.Meta(
            constraints={
                ('foo', 'bar'): Pair(Int(0, 15), operator.lt, Int(10, 20)),
            }
        )

    def update(self, candle: Candle) -> None:
        pass


def test_validate_strategy_constraints():
    Strategy.validate_constraints(DummyStrategy, 5, 15)
    with pytest.raises(ValueError):
        Strategy.validate_constraints(DummyStrategy, -5, 15)
        Strategy.validate_constraints(DummyStrategy, 5, 25)
        Strategy.validate_constraints(DummyStrategy, 11, 9)


def test_mid_trend_current() -> None:
    target = strategies.MidTrend(MidTrendPolicy.CURRENT)
    assert target.maturity == 1
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_mid_trend_previous() -> None:
    target = strategies.MidTrend(MidTrendPolicy.PREVIOUS)
    assert target.maturity == 2
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_mid_trend_ignore() -> None:
    target = strategies.MidTrend(MidTrendPolicy.IGNORE)
    assert target.maturity == 2
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.SHORT
    assert target.update(Advice.LONG) is Advice.LONG


def test_mid_trend_ignore_starting_with_none_does_not_ignore_first(
) -> None:
    target = strategies.MidTrend(MidTrendPolicy.IGNORE)
    assert target.update(Advice.NONE) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG


# def test_ignore_not_mature(
# ) -> None:
#     target = strategies.Maturity(maturity=2)
#     assert target.update(Advice.LONG) is Advice.NONE
#     assert target.update(Advice.LONG) is Advice.LONG
#     assert target.update(Advice.LONG) is Advice.LONG
#     assert target.update(Advice.SHORT) is Advice.SHORT


def test_persistence_level_0() -> None:
    target = strategies.Persistence(level=0)
    assert target.maturity == 1
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_persistence_level_1() -> None:
    target = strategies.Persistence(level=1)
    assert target.maturity == 2
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_persistence_level_1_return_previous() -> None:
    target = strategies.Persistence(level=1, return_previous=True)
    assert target.maturity == 2
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
    assert target.prevailing_advice is Advice.NONE
    assert target.prevailing_advice_age == 0

    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.prevailing_advice is Advice.LONG
    assert target.prevailing_advice_age == 2

    assert target.update(Advice.NONE) is Advice.NONE
    assert target.prevailing_advice is Advice.LONG
    assert target.prevailing_advice_age == 3

    assert target.update(Advice.SHORT) is Advice.SHORT
    assert target.prevailing_advice is Advice.SHORT
    assert target.prevailing_advice_age == 1


def test_mid_trend_persistence_combination() -> None:
    target1 = strategies.MidTrend(MidTrendPolicy.IGNORE)
    target2 = strategies.Persistence(level=1)

    assert Advice.combine(
        target1.update(Advice.SHORT),
        target2.update(Advice.SHORT),
    ) is Advice.NONE
    assert Advice.combine(
        target1.update(Advice.LONG),
        target2.update(Advice.LONG),
    ) is Advice.NONE
    assert Advice.combine(
        target1.update(Advice.LONG),
        target2.update(Advice.LONG),
    ) is Advice.LONG


def test_combine_advice() -> None:
    assert Advice.combine(Advice.NONE, Advice.LIQUIDATE) is Advice.NONE
    assert Advice.combine(Advice.NONE, Advice.LONG) is Advice.NONE
    assert Advice.combine(Advice.LONG, Advice.LIQUIDATE) is Advice.LIQUIDATE
    assert Advice.combine(Advice.LONG, Advice.LONG) is Advice.LONG
