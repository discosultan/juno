import operator
from decimal import Decimal
from random import Random

from juno import constraints


def test_constant_constraint() -> None:
    assert_constraint_chaos(constraints.Constant('foo'))


def test_choice_constraint() -> None:
    assert_constraint_chaos(constraints.Choice(['foo', 'bar']))


def test_constraint_choice_constraint() -> None:
    assert_constraint_chaos(constraints.ConstraintChoice([
        constraints.Constant(Decimal('0.0')),
        constraints.Uniform(Decimal('0.0001'), Decimal('0.9999')),
    ]))


def test_uniform_constraint() -> None:
    assert_constraint_chaos(constraints.Uniform(Decimal('-0.10'), Decimal('2.00')))


def test_int_constraint() -> None:
    assert_constraint_chaos(constraints.Int(-10, 10))


def test_int_pair_constraint() -> None:
    assert_constraint_chaos(
        constraints.Pair(constraints.Int(-10, 10), operator.lt, constraints.Int(5, 20))
    )


def assert_constraint_chaos(constraint: constraints.Constraint) -> None:
    random = Random()
    for _ in range(0, 1000):
        value = constraint.random(random)
    if isinstance(value, tuple):
        assert constraint.validate(*value)
    else:
        assert constraint.validate(value)
