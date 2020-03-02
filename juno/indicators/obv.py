from decimal import Decimal


# On-Balance Volume
class Obv:
    value: Decimal = Decimal('0.0')
    _last_price: Decimal = Decimal('0.0')
    _t: int = 0
    _t1: int = 0

    @property
    def req_history(self) -> int:
        return 0

    def update(self, volume: Decimal, price: Decimal) -> None:
        if price > self._last_price:
            self.value += volume
        elif price < self._last_price:
            self.value -= volume

        self._last_price = price
        self._t = min(self._t + 1, self._t1)
