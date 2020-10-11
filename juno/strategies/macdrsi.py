import operator
from decimal import Decimal

from juno import Advice, Candle
from juno.constraints import Int, Pair, Uniform

from .macd import Macd
from .rsi import Rsi
from .strategy import Meta, StrategyBase


class MacdRsi(StrategyBase):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                ('macd_short_period', 'macd_long_period'):
                    Pair(Int(1, 100), operator.lt, Int(2, 101)),
                'macd_signal_period': Int(1, 101),
                'rsi_period': Int(1, 101),
                'rsi_up_threshold': Uniform(Decimal('50.0'), Decimal('100.0')),
                'rsi_down_threshold': Uniform(Decimal('0.0'), Decimal('50.0')),
                'persistence': Int(0, 10),
            }
        )

    _macd: Macd
    _rsi: Rsi

    def __init__(
        self,
        macd_short_period: int = 12,
        macd_long_period: int = 26,
        macd_signal_period: int = 9,
        rsi_period: int = 14,
        rsi_up_threshold: Decimal = Decimal('70.0'),
        rsi_down_threshold: Decimal = Decimal('30.0'),
        persistence: int = 0,
    ) -> None:
        self._macd = Macd(macd_short_period, macd_long_period, macd_signal_period, 0)
        self._rsi = Rsi(rsi_period, rsi_up_threshold, rsi_down_threshold, 0)
        super().__init__(
            maturity=self._macd.maturity,
            persistence=persistence
        )
        self.validate(
            macd_short_period, macd_long_period, macd_signal_period, rsi_period, rsi_up_threshold,
            rsi_down_threshold, persistence
        )

    def tick(self, candle: Candle) -> Advice:
        return Advice.combine(self._macd.update(candle), self._rsi.update(candle))
