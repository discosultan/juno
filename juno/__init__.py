from collections import namedtuple
from enum import Enum

from juno.time import datetime_fromtimestamp_ms


AccountInfo = namedtuple('AccountInfo', ['time', 'base_balance', 'quote_balance', 'fees'])
BidAsk = namedtuple('BidAsk', ['price', 'qty'])
Depth = namedtuple('Depth', ['bids', 'asks'])
Fees = namedtuple('Fees', ['maker', 'taker'])
OrderResult = namedtuple('OrderResult', ['price', 'executed_qty'])
SymbolInfo = namedtuple('SymbolInfo', ['time', 'name', 'base_precision', 'quote_precision',
                                       'min_price', 'max_price', 'price_step_size',
                                       'min_qty', 'max_qty', 'qty_step_size'])
Trade = namedtuple('Trade', ['price', 'qty', 'commission', 'commission_asset', 'is_buyer'])


class Candle(namedtuple('Candle', ['time', 'open', 'high', 'low', 'close', 'volume'])):
    __slots__ = ()

    def __repr__(self):
        return (f'{self.__class__.__name__}(time={datetime_fromtimestamp_ms(self.time)}, '
                f'open={self.open}, high={self.high}, low={self.low}, close={self.close})')


class CandleRange(namedtuple('CandleRange', ['start', 'end'])):
    __slots__ = ()

    def __repr__(self):
        return (f'{self.__class__.__name__}(start={datetime_fromtimestamp_ms(self.start)}, '
                f'end={datetime_fromtimestamp_ms(self.end)})')


class Advice(Enum):
    LONG = 0
    SHORT = 1


class Side(Enum):
    BUY = 0
    SELL = 1


class OrderType(Enum):
    MARKET = 0
    LIMIT = 1
    STOP_LOSS = 2
    STOP_LOSS_LIMIT = 3
    TAKE_PROFIT = 4
    TAKE_PROFIT_LIMIT = 5
    LIMIT_MAKER = 6


class TimeInForce(Enum):
    # A Good-Til-Canceled order will continue to work within the system and in the marketplace
    # until it executes or is canceled.
    GTC = 0
    # Any portion of an Immediate-or-Cancel order that is not filled as soon as it becomes
    # available in the market is canceled.
    IOC = 1
    # If the entire Fill-or-Kill order does not execute as soon as it becomes available, the entire
    # order is canceled.
    FOK = 2
