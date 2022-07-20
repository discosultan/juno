from decimal import Decimal


# On-Balance Volume
class Obv:
    value: Decimal = Decimal("0.0")

    _last_price: Decimal = Decimal("0.0")
    _t: int = 0
    _t1: int = 1

    @property
    def maturity(self) -> int:
        return 0

    @property
    def mature(self) -> bool:
        return True

    def update(self, price: Decimal, volume: Decimal) -> Decimal:
        if self._t > 0:
            if price > self._last_price:
                self.value += volume
            elif price < self._last_price:
                self.value -= volume

        self._last_price = price
        self._t = min(self._t + 1, self._t1)
        return self.value
