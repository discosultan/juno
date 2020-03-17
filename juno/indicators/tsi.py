from decimal import Decimal

from .ema import Ema2 as Ema


# True Strength Index
class Tsi:
    value: Decimal = Decimal('0.0')
    _pc_ema_smoothed: Ema
    _pc_ema_dbl_smoothed: Ema
    _abs_pc_ema_smoothed: Ema
    _abs_pc_ema_dbl_smoothed: Ema
    _last_price: Decimal = Decimal('0.0')
    _t: int = 0
    _t1: int = 1
    _t2: int
    _t3: int

    # Common long: 25, short: 13
    def __init__(self, long_period: int, short_period: int) -> None:
        self._pc_ema_smoothed = Ema(long_period)
        self._pc_ema_dbl_smoothed = Ema(short_period)
        self._abs_pc_ema_smoothed = Ema(long_period)
        self._abs_pc_ema_dbl_smoothed = Ema(short_period)
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
            self.value = 100 * (
                self._pc_ema_dbl_smoothed.value / self._abs_pc_ema_dbl_smoothed.value
            )

        self._last_price = price
        self._t = min(self._t + 1, self._t3)
