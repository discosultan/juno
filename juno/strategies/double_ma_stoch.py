from typing import Any

from juno import Advice
from juno.candles import Candle
from juno.config import init_instance

from .double_ma import DoubleMA
from .stoch import Stoch
from .strategy import Signal


# Combines a double moving average with stochastic oscillator as a filter.
# https://www.tradingpedia.com/forex-trading-strategies/combining-stochastic-oscillator-and-emas/
class DoubleMAStoch(Signal):
    _advice: Advice = Advice.NONE
    _double_ma: DoubleMA
    _stoch: Stoch

    def __init__(
        self,
        double_ma: dict[str, Any],
        stoch: dict[str, Any],
    ) -> None:
        self._double_ma = init_instance(DoubleMA, double_ma)
        self._stoch = init_instance(Stoch, stoch)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        return max(self._double_ma.maturity, self._stoch.maturity)

    @property
    def mature(self) -> bool:
        return self._double_ma.mature and self._stoch.mature

    def update(self, candle: Candle) -> None:
        self._double_ma.update(candle)
        self._stoch.update(candle)

        if self.mature:
            # TODO: Try adding changed filter to MA output?
            ma_advice = self._double_ma.advice

            # Exit conditions.
            if (
                self._advice is Advice.LONG
                and (ma_advice is Advice.SHORT or self._stoch.overbought)
            ):
                self._advice = Advice.LIQUIDATE
            elif (
                self._advice is Advice.SHORT
                and (ma_advice is Advice.LONG or self._stoch.oversold)
            ):
                self._advice = Advice.LIQUIDATE

            # Entry conditions.
            if self._advice not in [Advice.LONG, Advice.SHORT]:
                if ma_advice is Advice.LONG and self._stoch.indicator.k < 50:
                    self._advice = Advice.LONG
                elif ma_advice is Advice.SHORT and self._stoch.indicator.k >= 50:
                    self._advice = Advice.SHORT
