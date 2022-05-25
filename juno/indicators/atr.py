from decimal import Decimal


# Average True Range
class Atr:
    value: Decimal = Decimal("0.0")

    _per: Decimal
    _t: int = 0
    _t1: int
    _t2: int
    _sum: Decimal = Decimal("0.0")
    _prev_close: Decimal

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f"Invalid period ({period})")

        self._per = Decimal("1.0") / period
        self._t1 = period
        self._t2 = period + 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t2)

        if self._t == 1:
            self._sum += high - low
        elif self._t <= self._t1:
            self._sum += _calc_truerange(high, low, self._prev_close)
            if self._t == self._t1:
                self.value = self._sum / self._t1
        else:
            self.value = (
                _calc_truerange(high, low, self._prev_close) - self.value
            ) * self._per + self.value

        self._prev_close = close
        return self.value


def _calc_truerange(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
    ych = abs(high - prev_close)
    ycl = abs(low - prev_close)
    v = high - low
    if ych > v:
        return ych
    if ycl > v:
        return ycl
    return v
