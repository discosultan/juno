from . import DI


# Directional Movement Index
class DX:

    def __init__(self, period):
        self.di = DI(period)

        self.t = 0
        self.t1 = period - 1

    @property
    def req_history(self):
        return self.t1

    def update(self, high, low, close):
        di_up, di_down = self.di.update(high, low, close)

        dx = None
        if self.t == self.t1:
            dm_diff = abs(di_up - di_down)
            dm_sum = di_up + di_down
            dx = dm_diff / dm_sum * 100.0

        self.t = min(self.t + 1, self.t1)

        return dx
