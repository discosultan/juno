import operator
from decimal import Decimal

from juno import Advice, Candle, math

from .macd import Macd
from .rsi import Rsi
from .strategy import Meta, Strategy


class MacdRsi(Strategy):
    @staticmethod
    def meta() -> Meta:
        return Meta(
            constraints={
                ('macd_short_period', 'macd_long_period'):
                    math.Pair(math.Int(1, 100), operator.lt, math.Int(2, 101)),
                'macd_signal_period': math.Int(1, 101),
                'rsi_period': math.Int(1, 101),
                'rsi_up_threshold': math.Uniform(Decimal('50.0'), Decimal('100.0')),
                'rsi_down_threshold': math.Uniform(Decimal('0.0'), Decimal('50.0')),
                'persistence': math.Int(0, 10),
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
        rsi_up_threshold: Decimal = Decimal('75.0'),
        rsi_down_threshold: Decimal = Decimal('25.0'),
        persistence: int = 0,
    ) -> None:
        self._macd = Macd(macd_short_period, macd_long_period, macd_signal_period, 0)
        self._rsi = Rsi(rsi_period, rsi_up_threshold, rsi_down_threshold, 0)
        super().__init__(
            maturity=max(self._macd.maturity, self._rsi.maturity),
            persistence=persistence
        )
        self.validate(
            macd_short_period, macd_long_period, macd_signal_period, rsi_period, rsi_up_threshold,
            rsi_down_threshold, persistence
        )

    def tick(self, candle: Candle) -> Advice:
        return Advice.combine(self._macd.update(candle), self._rsi.update(candle))
