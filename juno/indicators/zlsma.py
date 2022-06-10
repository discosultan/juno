from collections import deque
from decimal import Decimal
from typing import Sequence


# Zero Lag least Square Moving Average
# Ref: https://www.tradingview.com/script/3LGnSrQN-ZLSMA-Zero-Lag-LSMA/
# TODO: Fix!
class Zlsma:
    value: Decimal = Decimal("0.0")

    _period: int
    _offset: int
    _prices: deque[Decimal]
    _lsma: deque[Decimal]

    _periodMinusOne: int
    _sumX: Decimal
    _sumXSqr: Decimal
    _divisor: Decimal

    _t: int = 0
    _t1: int
    _t2: int

    def __init__(self, period: int = 32, offset: int = 0) -> None:
        if period < 2:
            raise ValueError(f"Invalid period ({period})")

        self._period = period
        self._offset = offset
        self._prices = deque(maxlen=period)
        self._lsma = deque(maxlen=period)

        self._periodMinusOne = period - 1
        periodTimesPeriodMinusOne = period * self._periodMinusOne
        self._sumX = periodTimesPeriodMinusOne * Decimal("0.5")
        self._sumXSqr = periodTimesPeriodMinusOne * (2 * period - 1) / Decimal("6.0")
        self._divisor = self._sumX**2 - period * self._sumXSqr

        self._t1 = period
        self._t2 = period * 2 - 1

    @property
    def maturity(self) -> int:
        return self._t2

    @property
    def mature(self) -> bool:
        return self._t >= self._t2

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t2)

        self._prices.append(price)

        if self._t >= self._t1:
            lsma = self._linreg(self._prices)
            self._lsma.append(lsma)

        if self._t >= self._t2:
            assert lsma
            lsma2 = self._linreg(self._lsma)
            eq = lsma - lsma2
            self.value = lsma + eq

        return self.value

    # Ref:
    # https://sourceforge.net/p/ta-lib/code/HEAD/tree/trunk/ta-lib/c/src/ta_func/ta_LINEARREG.c
    def _linreg(self, values: Sequence[Decimal]) -> Decimal:
        sumY = sum(values)
        sumXY = sum(i * p for i, p in enumerate(reversed(values), 1))
        m = (self._period * sumXY - self._sumX * sumY) / self._divisor
        b = (sumY - m * self._sumX) / self._period
        return b + m * self._periodMinusOne
