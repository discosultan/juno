from . import Sma


# Smoothed Moving Average
class Smma:

    def __init__(self, period):
        self.result = None
        self.sma = Sma(period)
        self.weight = period
        self.t = 0
        self.t1 = period - 1
        self.t2 = period

    @property
    def req_history(self):
        return self.t1

    def update(self, price):
        if self.t < self.t1:
            self.sma.update(price)
        elif self.t == self.t1:
            self.result = self.sma.update(price)
        else:
            self.result = (self.result * (self.weight - 1.0) + price) / self.weight

        self.t = min(self.t + 1, self.t2)
        return self.result
