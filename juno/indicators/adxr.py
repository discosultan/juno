from . import Adx
from collections import deque


# Average Directional Movement Index Rating
class Adxr:

    def __init__(self, period):
        self.adx = Adx(period)
        self.historical_adx = deque(maxlen=period)
        self.i = 0
        self.t = 0
        self.t1 = self.adx.req_history
        self.t2 = self.t1 + period - 1

    @property
    def req_history(self):
        return self.t2

    def update(self, high, low, close):
        adx = self.adx.update(high, low, close)

        result = None

        if self.t >= self.t1:
            self.historical_adx.append(adx)
        if self.t == self.t2:
            result = (adx + self.historical_adx.popleft()) / 2.0

        self.t = min(self.t + 1, self.t2)

        return result
