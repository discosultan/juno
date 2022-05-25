# The indicators are taken from (and verified against) the following sources:
# - https://github.com/TulipCharts/tulipindicators
# - https://github.com/voice32/stock_market_indicators
# - https://school.stockcharts.com/doku.php

from typing import Union

from .adx import Adx
from .adxr import Adxr
from .alma import Alma
from .atr import Atr
from .bbands import Bbands
from .cci import Cci
from .chaikin_oscillator import ChaikinOscillator
from .dema import Dema
from .di import DI
from .dm import DM
from .dx import DX
from .ema import Ema
from .ema2 import Ema2
from .kama import Kama
from .kvo import Kvo
from .macd import Macd
from .mmi import Mmi
from .momersion import Momersion
from .obv import Obv, Obv2
from .rsi import Rsi
from .sma import Sma
from .smma import Smma
from .stoch import Stoch
from .stochrsi import StochRsi
from .tsi import Tsi

MA = Union[Alma, Dema, Ema, Ema2, Kama, Sma, Smma]

__all__ = [
    "Adx",
    "Adxr",
    "Alma",
    "Atr",
    "Bbands",
    "Cci",
    "ChaikinOscillator",
    "Dema",
    "DI",
    "DM",
    "DX",
    "Ema",
    "Ema2",
    "Kama",
    "Kvo",
    "Macd",
    "MA",
    "Mmi",
    "Momersion",
    "Obv",
    "Obv2",
    "Rsi",
    "Sma",
    "Smma",
    "Stoch",
    "StochRsi",
    "Tsi",
]
