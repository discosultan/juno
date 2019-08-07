from decimal import Decimal
from typing import Generic, Type, TypeVar

from .ema import Ema

T = TypeVar('T', float, Decimal)


class Tsi(Generic[T]):
    # Common long: 25, short: 13
    def __init__(self, long_period: int, short_period: int,  # type: ignore
                 dec: Type[T] = Decimal) -> None:
        self.value: T = dec(0)
        self._pc_ema_smoothed: Ema[T] = Ema(long_period, v2=True, dec=dec)
        self._pc_ema_dbl_smoothed: Ema[T] = Ema(short_period, v2=True, dec=dec)
        self._abs_pc_ema_smoothed: Ema[T] = Ema(long_period, v2=True, dec=dec)
        self._abs_pc_ema_dbl_smoothed: Ema[T] = Ema(short_period, v2=True, dec=dec)
        self._last_price: T = dec(0)
        self._t = 0
        self._t1 = 1
        self._t2 = self._t1 + long_period - 1
        self._t3 = self._t2 + short_period - 1

    @property
    def req_history(self) -> int:
        return self._t3

    def update(self, price: T) -> None:
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
