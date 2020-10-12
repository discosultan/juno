from juno.constraints import Choice
from juno.indicators import Alma, Dema, Ema, Ema2, Kama, Sma, Smma
from juno.strategies import MidTrendPolicy

ma_choices = Choice([i.__name__.lower() for i in [Alma, Dema, Ema, Ema2, Kama, Sma, Smma]])
mid_trend_policy_choices = Choice([
    MidTrendPolicy.CURRENT,
    MidTrendPolicy.IGNORE,
    MidTrendPolicy.PREVIOUS,
])
