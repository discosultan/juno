import operator

import pytest

from juno import Advice, Candle, math, strategies


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


@pytest.mark.parametrize('maturity', [0, 1, 2])
def test_mature(maturity: int) -> None:
    strategy = strategies.Strategy(maturity=maturity)
    assert not strategy.mature

    for i in range(maturity + 1):
        strategy.update(Candle())
        assert strategy.mature == (i == maturity)


def test_mid_trend_ignore_false() -> None:
    target = strategies.MidTrend(ignore=False)
    assert target.maturity == 0
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_mid_trend_ignore_true() -> None:
    target = strategies.MidTrend(ignore=True)
    assert target.maturity == 1
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_mid_trend_ignore_starting_with_none_does_not_ignore_first(
) -> None:
    target = strategies.MidTrend(ignore=True)
    assert target.update(Advice.NONE) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG


# def test_ignore_not_mature(
# ) -> None:
#     target = strategies.IgnoreNotMatureAndMidTrend(maturity=1, ignore_mid_trend=False)
#     assert target.update(Advice.LONG) is Advice.NONE
#     assert target.update(Advice.LONG) is Advice.LONG
#     assert target.update(Advice.LONG) is Advice.LONG
#     assert target.update(Advice.SHORT) is Advice.SHORT


def test_persistence_level_0() -> None:
    target = strategies.Persistence(level=0)
    assert target.maturity == 0
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_persistence_level_1() -> None:
    target = strategies.Persistence(level=1)
    assert target.maturity == 1
    assert target.update(Advice.LONG) is Advice.NONE
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.LONG) is Advice.LONG
    assert target.update(Advice.SHORT) is Advice.NONE
    assert target.update(Advice.SHORT) is Advice.SHORT


def test_persistence_level_1_return_previous() -> None:
    target = strategies.Persistence(level=1, return_previous=True)
    assert target.maturity == 1
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


def test_mid_trend_persistence_combination() -> None:
    target1 = strategies.MidTrend(ignore=True)
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
