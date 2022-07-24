from decimal import Decimal

from .lsma import Lsma


# Zero Lag least Square Moving Average
# Ref: https://www.tradingview.com/script/3LGnSrQN-ZLSMA-Zero-Lag-LSMA/
class Zlsma:
    value: Decimal = Decimal("0.0")

    _lsma: Lsma
    _lsma2: Lsma

    _t: int = 0
    _t1: int
    _t2: int

    def __init__(self, period: int = 32) -> None:
        if period < 2:
            raise ValueError(f"Invalid period ({period})")

        self._period = period
        self._lsma = Lsma(period)
        self._lsma2 = Lsma(period)

        self._t1 = period * 2 - 1

    @property
    def maturity(self) -> int:
        return self._t1

    @property
    def mature(self) -> bool:
        return self._t >= self._t1

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t1)

        lsma = self._lsma.update(price)
        if self._lsma.mature:
            lsma2 = self._lsma2.update(lsma)
            if self._lsma2.mature:
                eq = lsma - lsma2
                self.value = lsma + eq

        return self.value
