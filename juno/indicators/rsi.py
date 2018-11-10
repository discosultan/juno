from . import Smma


# Relative Strength Index
class Rsi:

    def __init__(self, period):
        self.mean_down = Smma(period)
        self.mean_up = Smma(period)
        self.last_input = 0.0
        self.t = 0
        self.t1 = period

    @property
    def req_history(self):
        return self.t1

    def update(self, price):
        result = None
        if self.t > 0:
            up = 0.0
            down = 0.0
            if price > self.last_input:
                up = price - self.last_input
            elif price < self.last_input:
                down = self.last_input - price

            mean_up_result = self.mean_up.update(up)
            mean_down_result = self.mean_down.update(down)

            if self.t == self.t1:
                if mean_down_result == 0.0 and mean_up_result != 0.0:
                    result = 100.0
                elif mean_down_result == 0.0:
                    result = 0.0
                else:
                    rs = mean_up_result / mean_down_result
                    result = 100.0 - (100.0 / (1.0 + rs))

        self.last_input = price
        self.t = min(self.t + 1, self.t1)
        return result
