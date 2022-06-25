from typing import Any

from juno import Advice, Candle, CandleMeta, strategies
from juno.common import CandleType
from juno.config import init_module_instance
from juno.indicators import Sma
from juno.time import WEEK_MS

from .strategy import Changed, Signal


# TODO: Assumes strategy meta different than benchmark meta.
class Bmsb(Signal):
    _20w_sma: Sma
    _signal: Signal
    _advice: Advice = Advice.NONE
    _changed: Changed
    _is_over_20w_sma: bool = False
    _benchmark_meta: CandleMeta

    def __init__(
        self,
        signal: dict[str, Any],
        benchmark_symbol: str = "btc-usdt",
        benchmark_interval: int = WEEK_MS,
        benchmark_candle_type: CandleType = "regular",
    ) -> None:
        self._20w_sma: Sma = Sma(20)
        self._signal = init_module_instance(strategies, signal)
        self._changed = Changed(enabled=True)
        self._benchmark_meta = (benchmark_symbol, benchmark_interval, benchmark_candle_type)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        # TODO: Useless because the main interval can differ from benchmark one.
        return 0

    @property
    def mature(self) -> bool:
        return self._20w_sma.mature and self._signal.mature

    @property
    def extra_candles(self) -> list[CandleMeta]:
        return [
            self._benchmark_meta,
        ]

    def update(self, candle: Candle, meta: CandleMeta) -> Advice:
        if meta == self._benchmark_meta:
            self._20w_sma.update(candle.close)

            if self.mature:
                self._is_over_20w_sma = candle.close >= self._20w_sma.value
        else:
            self._signal.update(candle, meta)

            if self.mature:
                if self._is_over_20w_sma and self._signal.advice is Advice.LONG:
                    self._advice = Advice.LONG
                elif not self._is_over_20w_sma and self._signal.advice is Advice.SHORT:
                    self._advice = Advice.SHORT
                elif self._advice is Advice.LONG and not self._is_over_20w_sma:
                    self._advice = Advice.LIQUIDATE
                elif self._advice is Advice.SHORT and self._is_over_20w_sma:
                    self._advice = Advice.LIQUIDATE

        return self._changed.update(self._advice)
