# Simple Moving Average
class Sma:

    def __init__(self, period):
        if period < 1:
            raise ValueError(f'invalid period ({period})')

        self.inputs = [0.0] * period
        self.i = 0
        self.sum = 0.0
        self.t = 0
        self.t1 = period - 1

    @property
    def req_history(self):
        return self.t1

    def update(self, price):
        last = self.inputs[self.i]
        self.inputs[self.i] = price
        self.i = (self.i + 1) % len(self.inputs)
        self.sum = self.sum - last + price

        result = self.sum / len(self.inputs) if self.t == self.t1 else None

        self.t = min(self.t + 1, self.t1)

        return result
