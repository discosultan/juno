from decimal import Decimal

from .ema import Ema


class ChaikinOscillator:
    def __init__(self, short_period: int, long_period: int) -> None:
        self.value = Decimal('0.0')
        self._money_flow_volume = Decimal('0.0')
        self._short_ema = Ema.with_com(short_period, adjust=True)
        self._long_ema = Ema.with_com(long_period, adjust=True)

    @property
    def req_history(self) -> int:
        return 0

    def update(self, high: Decimal, low: Decimal, close: Decimal, volume: Decimal) -> None:
        if high != low:
            money_flow_multiplier = ((close - low) - (high - close)) / (high - low)
            self._money_flow_volume += money_flow_multiplier * volume

        self._short_ema.update(self._money_flow_volume)
        self._long_ema.update(self._money_flow_volume)
        self.value = self._short_ema.value - self._long_ema.value
