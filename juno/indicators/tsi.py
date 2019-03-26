from decimal import Decimal

from .ema import Ema


class Tsi:

    def __init__(self) -> None:
        self.pc_ema_1 = Ema(25)
        self.pc_ema_2 = Ema(13)
        self.abs_pc_ema_1 = Ema(25)
        self.abs_pc_ema_2 = Ema(13)
        self.last_price = Decimal(0)
        self.t = 0
        self.t1 = 1

    def update(self, price: Decimal) -> Decimal:
        result = Decimal(0)

        if self.t == self.t1:
            pc = price - self.last_price
            print(pc)

            smoothed_pc = self.pc_ema_1.update(pc)
            dbl_smoothed_pc = self.pc_ema_2.update(smoothed_pc)
            print(dbl_smoothed_pc)

            abs_pc = abs(pc)
            smoothed_abs_pc = self.abs_pc_ema_1.update(abs_pc)
            dbl_smoothed_abs_pc = self.abs_pc_ema_2.update(smoothed_abs_pc)
            print(dbl_smoothed_abs_pc)

            result = 100 * (dbl_smoothed_pc / dbl_smoothed_abs_pc)

        self.last_price = price
        self.t = min(self.t + 1, self.t1)
        return result
