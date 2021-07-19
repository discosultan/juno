from decimal import Decimal

from .ema import Ema


class ChaikinOscillator:
    def __init__(self, short_period: int, long_period: int) -> None:
        self.value = Decimal("0.0")
        self._money_flow_volume = Decimal("0.0")
        self._short_ema = Ema.with_com(short_period, adjust=True)
        self._long_ema = Ema.with_com(long_period, adjust=True)

    @property
    def maturity(self) -> int:
        return max(self._long_ema.maturity, self._short_ema.maturity)

    @property
    def mature(self) -> bool:
        return self._long_ema.mature and self._short_ema.mature

    def update(self, high: Decimal, low: Decimal, close: Decimal, volume: Decimal) -> Decimal:
        if high != low:
            money_flow_multiplier = ((close - low) - (high - close)) / (high - low)
            self._money_flow_volume += money_flow_multiplier * volume

        self._short_ema.update(self._money_flow_volume)
        self._long_ema.update(self._money_flow_volume)

        self.value = self._short_ema.value - self._long_ema.value
        return self.value
