from . import DM


# Directional Indicator
class DI:

    def __init__(self, period):
        self.dm = DM(period)
        self.atr = 0.0
        self.per = (period - 1) / period

        self.prev_close = None

        self.t = 0
        self.t1 = 1
        self.t2 = period - 1
        self.t3 = period

    @property
    def req_history(self):
        return self.t1

    def update(self, high, low, close):
        plus_dm, minus_dm = self.dm.update(high, low)

        plus_di, minus_di = None, None

        if self.t >= self.t1 and self.t < self.t3:
            self.atr += _calc_truerange(self.prev_close, high, low)

        if self.t == self.t2:
            plus_di  = 100.0 * plus_dm / self.atr
            minus_di = 100.0 * minus_dm / self.atr
        elif self.t == self.t3:
            self.atr = self.atr * self.per + _calc_truerange(self.prev_close, high, low)
            plus_di  = 100.0 * plus_dm / self.atr
            minus_di = 100.0 * minus_dm / self.atr

        self.prev_close = close
        self.t = min(self.t + 1, self.t3)

        return plus_di, minus_di


def _calc_truerange(prev_close, high, low):
    ych = abs(high - prev_close)
    ycl = abs(low - prev_close)
    v = high - low
    if ych > v:
        v = ych
    if ycl > v:
        v = ycl
    return v
