# Indicators are adapted and verified using the Tulip Indicators C library:
# https://github.com/TulipCharts/tulipindicators

import inspect
import sys
from typing import Any, Type

from .adx import Adx
from .adxr import Adxr
from .cci import Cci
from .dema import Dema
from .di import DI
from .dm import DM
from .dx import DX
from .ema import Ema, Ema2
from .macd import Macd
from .rsi import Rsi
from .sma import Sma
from .smma import Smma
from .stoch import Stoch
from .stochrsi import StochRsi
from .tsi import Tsi

__all__ = [
    'Adx',
    'Adxr',
    'Cci',
    'Dema',
    'DI',
    'DM',
    'DX',
    'Ema',
    'Ema2',
    'Macd',
    'Rsi',
    'Sma',
    'Smma',
    'Stoch',
    'StochRsi',
    'Tsi',
]

_indicators = {
    name.lower(): obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
}


def get_indicator_type(name: str) -> Type[Any]:
    return _indicators[name]
