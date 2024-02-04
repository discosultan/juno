# The indicators are taken from (and verified against) the following sources:
# - https://github.com/TulipCharts/tulipindicators
# - https://github.com/voice32/stock_market_indicators
# - https://school.stockcharts.com
# - https://stockcharts.com
# - https://tradingview.com

from typing import Union

from .adx import Adx
from .adxr import Adxr
from .alma import Alma
from .atr import Atr
from .atr2 import Atr2
from .bbands import Bbands
from .cci import Cci
from .cci2 import Cci2
from .chaikin_oscillator import ChaikinOscillator
from .chandelier_exit import ChandelierExit
from .darvas_box import DarvasBox
from .dema import Dema
from .di import DI
from .dm import DM
from .dx import DX
from .ema import Ema
from .ema2 import Ema2
from .kama import Kama
from .kvo import Kvo
from .lsma import Lsma
from .macd import Macd
from .mmi import Mmi
from .momersion import Momersion
from .obv import Obv
from .obv2 import Obv2
from .rsi import Rsi
from .sma import Sma
from .smma import Smma
from .stoch import Stoch
from .stochrsi import StochRsi
from .tsi import Tsi
from .wma import Wma
from .zlsma import Zlsma

MA = Union[Alma, Dema, Ema, Ema2, Kama, Sma, Smma, Wma]

__all__ = [
    "Adx",
    "Adxr",
    "Alma",
    "Atr",
    "Atr2",
    "Bbands",
    "Cci",
    "Cci2",
    "ChaikinOscillator",
    "ChandelierExit",
    "DarvasBox",
    "Dema",
    "DI",
    "DM",
    "DX",
    "Ema",
    "Ema2",
    "Kama",
    "Kvo",
    "Lsma",
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
    "Wma",
    "Zlsma",
]
