from decimal import Decimal

from .ema2 import Ema2 as Ema


class Tsi:

    # Common long: 25, short: 13
    def __init__(self, long_period: int, short_period: int) -> None:
        self.pc_ema_1 = Ema(long_period)
        self.pc_ema_2 = Ema(short_period)
        self.abs_pc_ema_1 = Ema(long_period)
        self.abs_pc_ema_2 = Ema(short_period)
        self.last_price = Decimal(0)
        self.t = 0
        self.t1 = 1
        self.t2 = self.t1 + long_period - 1
        self.t3 = self.t2 + short_period - 1

    @property
    def req_history(self) -> int:
        return self.t3

    def update(self, price: Decimal) -> Decimal:
        result = Decimal(0)

        if self.t >= self.t1:
            pc = price - self.last_price
            smoothed_pc = self.pc_ema_1.update(pc)
            abs_pc = abs(pc)
            smoothed_abs_pc = self.abs_pc_ema_1.update(abs_pc)

        if self.t >= self.t2:
            dbl_smoothed_pc = self.pc_ema_2.update(smoothed_pc)
            dbl_smoothed_abs_pc = self.abs_pc_ema_2.update(smoothed_abs_pc)

        if self.t == self.t3:
            result = 100 * (dbl_smoothed_pc / dbl_smoothed_abs_pc)

        self.last_price = price
        self.t = min(self.t + 1, self.t3)
        return result
