import operator

import pytest

from juno import math
from juno.strategies import Meta, Strategy


def test_meta():
    meta = Meta(
        params={
            'foo': {},
            'bar': {},
            'baz': {},
        },
        identifier='{foo}{bar}hello'
    )
    assert meta.identifier_params == ['foo', 'bar']
    assert meta.non_identifier_params == ['baz']


def test_strategy_meta():
    strategy = DummyStrategy()

    strategy.validate(5, 15)
    with pytest.raises(ValueError):
        strategy.validate(-5, 15)
        strategy.validate(5, 25)
        strategy.validate(11, 9)


class DummyStrategy(Strategy):

    @staticmethod
    def meta():
        return Meta(
            params={
                'foo': math.Int(0, 15),
                'bar': math.Int(10, 20),
            },
            constraints={
                ('foo', 'bar'): operator.lt,
            }
        )

    def req_history(self):
        pass

    def update(self, candle):
        pass
