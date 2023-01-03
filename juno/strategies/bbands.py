from decimal import Decimal

from juno import Advice, Candle, CandleMeta, Interval_
from juno.indicators import Bbands, Obv
from juno.strategies.strategy import Changed

from .strategy import Signal

# 3m
# 24h -> 480 candles
# 2h  -> 40 candles
# 1h  -> 20 candles
# 30m -> 10 candles
# 15m -> 5 candles
_num_3m_candles = 20

# 5m
# 24h -> 288 candles
# 2h  -> 24 candles
# 1h  -> 12 candles
# 30m -> 6 candles
# 15m -> 3 candles
_num_5m_candles = 12


# TODO: Assumes 1m candle as main.
class BBands(Signal):
    def __init__(self) -> None:
        self._bb = Bbands(20, Decimal("2.0"))
        self._3m_candles: list[Candle] = []
        self._5m_candles: list[Candle] = []
        self._previous_trend = 0  # 1 up; 0 none; -1 down
        self._trend = 0
        self._previous_outside_bb = 0  # 1 outside upper; 0 inside; -1 outside lower
        self._outside_bb = 0
        self._advice = Advice.NONE
        self._changed = Changed(enabled=True)

    @property
    def advice(self) -> Advice:
        return self._advice

    @property
    def maturity(self) -> int:
        # TODO: Useless because of multiple candle intervals.
        return 0

    @property
    def mature(self) -> bool:
        return (
            self._bb.mature
            and len(self._3m_candles) == _num_3m_candles
            and len(self._5m_candles) == _num_5m_candles
        )

    @property
    def extra_candles(self) -> list[CandleMeta]:
        # TODO
        return [
            ("btc-usdt", 3 * Interval_.MIN, "regular"),
            ("btc-usdt", 5 * Interval_.MIN, "regular"),
        ]

    def update(self, candle: Candle, candle_meta: CandleMeta) -> None:
        _, interval, _ = candle_meta

        if interval == Interval_.MIN:
            self._update_1m(candle)
        elif interval == 3 * Interval_.MIN:
            self._update_3m(candle)
        elif interval == 5 * Interval_.MIN:
            self._update_5m(candle)
        else:
            raise ValueError("Unexpected candle interval")

        self._advice = self._changed.update(self._advice)

    def _update_1m(self, candle: Candle) -> None:
        # Update current outside bb.
        self._bb.update(candle.close)
        self._outside_bb = (
            1 if candle.close > self._bb.upper else -1 if candle.close < self._bb.lower else 0
        )

        if self.mature:
            # Update current trend.
            obv3 = Obv()
            for candle3 in self._3m_candles:
                obv3.update(candle3.close, candle3.volume)
            obv5 = Obv()
            for candle5 in self._5m_candles:
                obv5.update(candle5.close, candle5.volume)

            self._trend = (
                1
                if obv3.value > 0 and obv5.value > 0
                else -1
                if obv3.value < 0 and obv5.value < 0
                else 0
            )

            # Update advice.

            # Open position if previous outside bb and current back in.
            # if self._previous_outside_bb == -1 and self._outside_bb == 0:
            #     self._advice = Advice.LONG
            # elif self._previous_outside_bb == 1 and self._outside_bb == 0:
            #     self._advice = Advice.SHORT

            # Open position if previous outside bb and current back in and is matching trend.
            if self._previous_outside_bb == -1 and self._outside_bb == 0 and self._trend == 1:
                self._advice = Advice.LONG
            elif self._previous_outside_bb == 1 and self._outside_bb == 0 and self._trend == -1:
                self._advice = Advice.SHORT

            # Close position if trend turns opposite.
            # elif self._advice is Advice.LONG and self._trend == -1:
            #     self._advice = Advice.LIQUIDATE
            # elif self._advice is Advice.SHORT and self._trend == 1:
            #     self._advice = Advice.LIQUIDATE

            # Close position if trend turns opposite or neutral.
            elif self._advice is Advice.LONG and self._trend != 1:
                self._advice = Advice.LIQUIDATE
            elif self._advice is Advice.SHORT and self._trend != -1:
                self._advice = Advice.LIQUIDATE

            # Close position if outside bb on the opposite side from opening.
            elif self._advice is Advice.LONG and self._outside_bb == 1:
                self._advice = Advice.LIQUIDATE
            elif self._advice is Advice.SHORT and self._outside_bb == -1:
                self._advice = Advice.LIQUIDATE

        # Update previous outside bb and trend.
        self._previous_outside_bb = self._outside_bb
        self._previous_trend = self._trend

    def _update_3m(self, candle: Candle) -> None:
        if len(self._3m_candles) == _num_3m_candles:
            self._3m_candles.pop(0)
        self._3m_candles.append(candle)

    def _update_5m(self, candle: Candle) -> None:
        if len(self._5m_candles) == _num_5m_candles:
            self._5m_candles.pop(0)
        self._5m_candles.append(candle)
