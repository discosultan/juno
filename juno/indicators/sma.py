from decimal import Decimal


# Simple Moving Average
class Sma:
    value: Decimal = Decimal("0.0")
    _prices: list[Decimal]
    _i: int = 0
    _sum: Decimal = Decimal("0.0")
    _t: int = 0
    _t1: int

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f"Invalid period ({period})")

        self._prices = [Decimal("0.0")] * period
        self._t1 = period

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        last = self._prices[self._i]
        self._prices[self._i] = price
        self._i = (self._i + 1) % len(self._prices)
        self._sum = self._sum - last + price
        self.value = self._sum / len(self._prices)

        return self.value
