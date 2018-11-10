# Directional Movement Indicator
class DM:

    def __init__(self, period):
        if period < 1:
            raise ValueError(f'invalid period ({period})')

        self.per = (period - 1) / period

        self.dmup, self.dmdown = 0.0, 0.0
        self.prev_high, self.prev_low = None, None

        self.t = 0
        self.t1 = 1
        self.t2 = period - 1
        self.t3 = period

    @property
    def req_history(self):
        return self.t2

    def update(self, high, low):
        plus_dm, minus_dm = None, None

        if self.t >= self.t1 and self.t < self.t3:
            dp, dm = _calc_direction(self.prev_high, self.prev_low, high, low)
            self.dmup += dp
            self.dmdown += dm

        if self.t == self.t2:
            plus_dm, minus_dm = self.dmup, self.dmdown
        elif self.t == self.t3:
            dp, dm = _calc_direction(self.prev_high, self.prev_low, high, low)
            self.dmup = self.dmup * self.per + dp
            self.dmdown = self.dmdown * self.per + dm
            plus_dm, minus_dm = self.dmup, self.dmdown

        self.prev_high, self.prev_low = high, low
        self.t = min(self.t + 1, self.t3)

        return plus_dm, minus_dm


def _calc_direction(prev_high, prev_low, high, low):
    up = high - prev_high
    down = prev_low - low

    if up < 0.0:
        up = 0.0
    elif up > down:
        down = 0.0

    if down < 0.0:
        down = 0.0
    elif down > up:
        up = 0.0

    return up, down
