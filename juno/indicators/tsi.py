from decimal import Decimal

from .ema_2 import Ema2 as Ema


class Tsi:

    def __init__(self) -> None:
        self.pc_ema_1 = Ema(25)
        self.pc_ema_2 = Ema(13)
        self.abs_pc_ema_1 = Ema(25)
        self.abs_pc_ema_2 = Ema(13)
        self.last_price = Decimal(0)
        self.t = 0
        self.t1 = 1
        self.t2 = self.t1 + 25
        self.t3 = self.t2 + 13

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
