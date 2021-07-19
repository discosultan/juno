from decimal import Decimal

from .ema2 import Ema2


# True Strength Index
class Tsi:
    value: Decimal = Decimal("0.0")
    _pc_ema_smoothed: Ema2
    _pc_ema_dbl_smoothed: Ema2
    _abs_pc_ema_smoothed: Ema2
    _abs_pc_ema_dbl_smoothed: Ema2
    _last_price: Decimal = Decimal("0.0")
    _t: int = 0
    _t1: int = 2
    _t2: int
    _t3: int

    # Common long: 25, short: 13
    def __init__(self, long_period: int, short_period: int) -> None:
        self._pc_ema_smoothed = Ema2(long_period)
        self._pc_ema_dbl_smoothed = Ema2(short_period)
        self._abs_pc_ema_smoothed = Ema2(long_period)
        self._abs_pc_ema_dbl_smoothed = Ema2(short_period)
        self._t2 = long_period + 1
        self._t3 = self._t2 + short_period - 1

    @property
    def maturity(self) -> int:
        return self._t3

    @property
    def mature(self) -> bool:
        return self._t >= self._t3

    def update(self, price: Decimal) -> Decimal:
        self._t = min(self._t + 1, self._t3)

        if self._t >= self._t1:
            pc = price - self._last_price
            self._pc_ema_smoothed.update(pc)
            abs_pc = abs(pc)
            self._abs_pc_ema_smoothed.update(abs_pc)

        if self._t >= self._t2:
            self._pc_ema_dbl_smoothed.update(self._pc_ema_smoothed.value)
            self._abs_pc_ema_dbl_smoothed.update(self._abs_pc_ema_smoothed.value)

        if self._t >= self._t3:
            self.value = 100 * (
                self._pc_ema_dbl_smoothed.value / self._abs_pc_ema_dbl_smoothed.value
            )

        self._last_price = price
        return self.value
