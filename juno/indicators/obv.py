from decimal import Decimal

from .ema import Ema


# On-Balance Volume
class Obv:
    value: Decimal = Decimal('0.0')
    ema: Decimal = Decimal('0.0')
    _ema: Ema
    _last_price: Decimal = Decimal('0.0')
    _t: int = 0
    _t1: int = 0

    def __init__(self) -> None:
        self._ema = Ema.with_com(21, adjust=True)

    @property
    def req_history(self) -> int:
        return 0

    def update(self, price: Decimal, volume: Decimal) -> None:
        if price > self._last_price:
            self.value += volume
        elif price < self._last_price:
            self.value -= volume

        self._ema.update(self.value)
        self.ema = self._ema.value

        self._last_price = price
        self._t = min(self._t + 1, self._t1)
