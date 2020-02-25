from decimal import Decimal


# On-Balance Volume
class Obv:
    def __init__(self) -> None:
        self.value = Decimal('0.0')
        self.ema = Decimal('0.0')
        self._last_price = Decimal('0.0')
        self._t = 0
        self._t1 = 0

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
