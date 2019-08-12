from decimal import Decimal

from juno import Candle
from juno_rs import emaemacx  # noqa

candles = [Candle(1, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(1), True)]
fees = (0.0, 2.0)
quote2 = 0.0

candles_converted = [
    (c[0], float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]), c[6])
    for c in candles
]

print(emaemacx(candles_converted, fees, quote2))
