from decimal import Decimal

from .ema import Ema


class Obv2:
    value: Decimal = Decimal("0.0")
    ema: Decimal = Decimal("0.0")
    _ema: Ema
    _last_price: Decimal = Decimal("0.0")

    def __init__(self, period: int) -> None:
        self._ema = Ema.with_com(period, adjust=True)

    @property
    def maturity(self) -> int:
        return 0

    @property
    def mature(self) -> bool:
        return True

    def update(self, price: Decimal, volume: Decimal) -> tuple[Decimal, Decimal]:
        if price > self._last_price:
            self.value += volume
        elif price < self._last_price:
            self.value -= volume

        self.ema = self._ema.update(self.value)

        self._last_price = price
        return self.value, self.ema
