# The indicators are taken from (and verified against) the following sources:
# - https://github.com/TulipCharts/tulipindicators
# - https://github.com/voice32/stock_market_indicators
# - https://school.stockcharts.com/doku.php

from typing import Union

from .adx import Adx
from .adxr import Adxr
from .cci import Cci
from .chaikin_oscillator import ChaikinOscillator
from .dema import Dema
from .di import DI
from .dm import DM
from .dx import DX
from .ema import Ema, Ema2
from .kama import Kama
from .kvo import Kvo
from .macd import Macd
from .obv import Obv, Obv2
from .rsi import Rsi
from .sma import Sma
from .smma import Smma
from .stoch import Stoch
from .stochrsi import StochRsi
from .tsi import Tsi

MA = Union[Dema, Ema, Ema2, Kama, Sma, Smma]

__all__ = [
    'Adx',
    'Adxr',
    'Cci',
    'ChaikinOscillator',
    'Dema',
    'DI',
    'DM',
    'DX',
    'Ema',
    'Ema2',
    'Kama',
    'Kvo',
    'Macd',
    'MA',
    'Obv',
    'Obv2',
    'Rsi',
    'Sma',
    'Smma',
    'Stoch',
    'StochRsi',
    'Tsi',
]
