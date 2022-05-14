from decimal import Decimal


# Bollinger Bands
class Bbands:
    upper: Decimal = Decimal("0.0")
    middle: Decimal = Decimal("0.0")
    lower: Decimal = Decimal("0.0")

    _stddev: Decimal
    _sum: Decimal = Decimal("0.0")
    _sum2: Decimal = Decimal("0.0")
    _prices: list[Decimal]
    _t: int = 0
    _t1: int

    def __init__(self, period: int, stddev: Decimal) -> None:
        if period < 1:
            raise ValueError(f"Invalid period ({period})")

        self._stddev = stddev
        self._scale = Decimal("1.0") / period
        self._prices = []
        self._t1 = period

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        self._t = min(self._t + 1, self._t1)

        self._sum += price
        self._sum2 += price**2

        if self._t >= self._t1:
            sd = (self._sum2 * self._scale - (self._sum * self._scale) ** 2).sqrt()
            self.middle = self._sum * self._scale
            self.upper = self.middle + self._stddev * sd
            self.lower = self.middle - self._stddev * sd

            old_price = self._prices.pop(0)
            self._sum -= old_price
            self._sum2 -= old_price**2

        self._prices.append(price)
        return self.lower, self.middle, self.upper
