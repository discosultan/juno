from contextlib import asynccontextmanager
from decimal import Decimal

from juno import (
    Fees, Filters, OrderResult, OrderStatus, Side, SymbolsInfo, brokers, components, exchanges
)


class Exchange(exchanges.Exchange):
    def __init__(
        self,
        historical_candles=[],
        future_candles=[],
        symbol_info=SymbolsInfo(
            fees={'__all__': Fees.none()},
            filters={'__all__': Filters.none()}
        ),
        balances=None,
        future_balances=[],
        depth=None,
        future_depths=[],
        future_orders=[],
        place_order_result=None,
    ):
        super().__init__()
        self.historical_candles = historical_candles
        self.future_candles = future_candles
        self.symbol_info = symbol_info
        self.balances = balances
        self.future_balances = future_balances
        self.depth = depth
        self.future_depths = future_depths
        self.future_orders = future_orders
        self.place_order_result = place_order_result

    async def get_symbols_info(self):
        return self.symbol_info

    async def get_balances(self):
        return self.balances

    @asynccontextmanager
    async def connect_stream_balances(self):
        async def inner():
            for balance in self.future_balances:
                yield balance

        yield inner()

    async def stream_historical_candles(self, symbol, interval, start, end):
        for c in (c for c in self.historical_candles if c.time >= start and c.time < end):
            yield c

    @asynccontextmanager
    async def connect_stream_candles(self, symbol, interval):
        async def inner():
            for c in (c for c in self.future_candles):
                yield c

        yield inner()

    async def get_depth(self, symbol):
        return self.depth

    @asynccontextmanager
    async def connect_stream_depth(self, symbol):
        async def inner():
            for depth in self.future_depths:
                yield depth

        yield inner()

    @asynccontextmanager
    async def connect_stream_orders(self):
        async def inner():
            for order in self.future_orders:
                yield order

        yield inner()

    async def place_order(self, *args, **kwargs):
        return self.place_order_result

    async def cancel_order(self, *args, **kwargs):
        pass


class Chandler:
    def __init__(self, candles):
        self.candles = candles

    async def stream_candles(self, exchange, symbol, interval, start, end):
        for candle in self.candles:
            yield candle


class Informant:
    def __init__(self, fees=Fees.none(), filters=Filters.none()):
        self.fees = fees
        self.filters = filters

    def get_fees_filters(self, exchange, symbol):
        return self.fees, self.filters


class Orderbook(components.Orderbook):
    def __init__(self, data):
        self._data = data


class Wallet:
    def __init__(self, exchange_balances):
        self._exchange_balances = exchange_balances

    def get_balance(self, exchange, asset):
        return self._exchange_balances[exchange][asset]


class Market(brokers.Market):
    def __init__(self, informant, orderbook, update_orderbook):
        self._informant = informant
        self._orderbook = orderbook
        self._update_orderbook = update_orderbook

    async def buy(self, exchange, symbol, quote, test):
        fills = super().find_order_asks(exchange=exchange, symbol=symbol, quote=quote)
        if self._update_orderbook:
            self._remove_from_orderbook(exchange, symbol, Side.BUY, fills)
        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    async def sell(self, exchange, symbol, base, test):
        fills = super().find_order_bids(exchange=exchange, symbol=symbol, base=base)
        if self._update_orderbook:
            self._remove_from_orderbook(exchange, symbol, Side.SELL, fills)
        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    def _remove_from_orderbook(self, exchange, symbol, side, fills):
        orderbook_side = self._orderbook._data[exchange][symbol][side]
        for fill in fills:
            orderbook_side[fill.price] -= fill.size
            if orderbook_side[fill.price] == Decimal(0):
                del orderbook_side[fill.price]


class Strategy:
    def __init__(self, *advices):
        self.advices = list(reversed(advices))

    def update(self, candle):
        return self.advices.pop()


def Time():
    time = -1

    def get_time():
        nonlocal time
        time += 1
        return time

    return get_time
