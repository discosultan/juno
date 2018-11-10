from . import DX, Smma


# Average Directional Index
class Adx:

    def __init__(self, period):
        if period < 2:
            raise ValueError(f'invalid period ({period})')

        self.dx = DX(period)
        self.smma = Smma(period)
        self.t1 = (period - 1) * 2

    @property
    def req_history(self):
        return self.t1

    def update(self, high, low, close):
        dx = self.dx.update(high, low, close)
        return None if dx is None else self.smma.update(dx)
