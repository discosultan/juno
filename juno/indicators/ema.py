# Exponential Moving Average
class Ema:

    def __init__(self, period):
        if period < 1:
            raise ValueError(f'invalid period ({period})')

        self.a = 2.0 / (period + 1)  # Smoothing factor.
        self.result = None
        self.t = 0

    @property
    def req_history(self):
        return 0

    def update(self, price):
        if self.t == 0:
            self.result = price
            self.t = 1
        else:
            self.result = (price - self.result) * self.a + self.result

        return self.result

    @staticmethod
    def with_smoothing(a):
        dummy_period = 1
        ema = Ema(dummy_period)
        ema.a = a
        return ema
