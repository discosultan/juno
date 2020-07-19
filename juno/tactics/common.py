from juno.constraints import Choice
from juno.indicators import Alma, Dema, Ema, Ema2, Kama, Sma, Smma

ma_choices = Choice([i.__name__.lower() for i in [Alma, Dema, Ema, Ema2, Kama, Sma, Smma]])
