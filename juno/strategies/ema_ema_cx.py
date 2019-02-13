from juno import Candle
from juno.indicators import Ema
from juno.utils import Trend


class EmaEmaCX:

    def __init__(self, short_period: int, long_period: int, neg_threshold: float,
                 pos_threshold: float, persistence: int) -> None:
        if neg_threshold > 0.0 or pos_threshold < 0.0:
            raise ValueError(f'neg threshold ({neg_threshold}) must be negative; pos threshold '
                             f'({pos_threshold}) positive')
        if long_period <= short_period:
            raise ValueError(f'long period ({long_period}) must be bigger than short period '
                             f'({short_period})')

        self.ema_short = Ema(short_period)
        self.ema_long = Ema(long_period)
        self.neg_threshold = neg_threshold
        self.pos_threshold = pos_threshold
        self.trend = Trend(persistence)
        self.t = 0
        self.t1 = long_period - 1

    @property
    def req_history(self) -> int:
        return self.t1

    def update(self, candle: Candle) -> int:
        short_ema_result = self.ema_short.update(candle.close)
        long_ema_result = self.ema_long.update(candle.close)

        trend_dir = 0
        if self.t == self.t1:
            diff = 100 * (short_ema_result - long_ema_result) / ((
                short_ema_result + long_ema_result) / 2)

            if diff > self.pos_threshold:
                trend_dir = 1
            elif diff < self.neg_threshold:
                trend_dir = -1

        self.t = min(self.t + 1, self.t1)
        return self.trend.update(trend_dir)
