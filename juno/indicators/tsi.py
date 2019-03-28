from decimal import Decimal

from .ema2 import Ema2 as Ema


class Tsi:

    # Common long: 25, short: 13
    def __init__(self, long_period: int, short_period: int) -> None:
        self.value = Decimal(0)
        self._pc_ema_smoothed = Ema(long_period)
        self._pc_ema_dbl_smoothed = Ema(short_period)
        self._abs_pc_ema_smoothed = Ema(long_period)
        self._abs_pc_ema_dbl_smoothed = Ema(short_period)
        self._last_price = Decimal(0)
        self._t = 0
        self._t1 = 1
        self._t2 = self._t1 + long_period - 1
        self._t3 = self._t2 + short_period - 1

    @property
    def req_history(self) -> int:
        return self._t3

    def update(self, price: Decimal) -> None:
        if self._t >= self._t1:
            pc = price - self._last_price
            self._pc_ema_smoothed.update(pc)
            abs_pc = abs(pc)
            self._abs_pc_ema_smoothed.update(abs_pc)

        if self._t >= self._t2:
            self._pc_ema_dbl_smoothed.update(self._pc_ema_smoothed.value)
            self._abs_pc_ema_dbl_smoothed.update(self._abs_pc_ema_smoothed.value)

        if self._t == self._t3:
            self.value = 100 * (self._pc_ema_dbl_smoothed.value /
                                self._abs_pc_ema_dbl_smoothed.value)

        self._last_price = price
        self._t = min(self._t + 1, self._t3)
