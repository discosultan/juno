from . import Ema


# Double Exponential Moving Average
class Dema:

    def __init__(self, period):
        self.ema1 = Ema(period)
        self.ema2 = Ema(period)
        self.t = 0
        self.t1 = period - 1
        self.t2 = self.t1 * 2

    @property
    def req_history(self):
        return self.t2

    def update(self, price):
        result = None
        ema1_result = self.ema1.update(price)

        if self.t <= self.t1:
            self.ema2.update(price)

        if self.t >= self.t1:
            ema2_result = self.ema2.update(ema1_result)
            if self.t == self.t2:
                result = ema1_result * 2.0 - ema2_result

        self.t = min(self.t + 1, self.t2)
        return result
