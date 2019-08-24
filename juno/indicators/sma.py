from decimal import Decimal


# Simple Moving Average
class Sma:
    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f'Invalid period ({period})')

        self.value = Decimal(0)
        self._prices = [Decimal(0)] * period
        self._i = 0
        self._sum = Decimal(0)
        self._t = 0
        self._t1 = period - 1

    @property
    def req_history(self) -> int:
        return self._t1

    def update(self, price: Decimal) -> None:
        last = self._prices[self._i]
        self._prices[self._i] = price
        self._i = (self._i + 1) % len(self._prices)
        self._sum = self._sum - last + price
        self.value = self._sum / len(self._prices)

        self._t = min(self._t + 1, self._t1)
