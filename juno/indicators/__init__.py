# The indicators are taken from (and verified against) the following sources:
# - https://github.com/TulipCharts/tulipindicators
# - https://github.com/voice32/stock_market_indicators
# - https://school.stockcharts.com/doku.php

from abc import ABC, abstractmethod
from decimal import Decimal

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


class MovingAverage(ABC):
    value: Decimal

    @abstractmethod
    def update(self, price: Decimal) -> Decimal:
        ...


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
    'MovingAverage',
    'Obv',
    'Obv2',
    'Rsi',
    'Sma',
    'Smma',
    'Stoch',
    'StochRsi',
    'Tsi',
]
