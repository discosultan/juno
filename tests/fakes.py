from contextlib import asynccontextmanager
from decimal import Decimal

from juno import Fees, Filters, OrderResult, OrderStatus, Side, brokers, components, exchanges


class Exchange(exchanges.Exchange):
    def __init__(
        self,
        candles=[],
        fees={'__all__': Fees.none()},
        filters={'__all__': Filters.none()},
        balances=[],
        depths=[],
        orders=[]
    ):
        self.candles = candles
        self.fees = fees
        self.filters = filters
        self.balances = balances
        self.depths = depths
        self.orders = orders

    async def map_fees(self):
        return self.fees

    async def map_filters(self):
        return self.filters

    @asynccontextmanager
    async def connect_stream_balances(self):
        async def inner():
            for balance in self.balances:
                yield balance

        yield inner()

    @asynccontextmanager
    async def connect_stream_candles(self, symbol, interval, start, end):
        async def inner():
            for c in (c for c in self.candles if c.time >= start and c.time < end):
                yield c

        yield inner()

    @asynccontextmanager
    async def connect_stream_depth(self, symbol):
        async def inner():
            for depth in self.depths:
                yield depth

        yield inner()

    @asynccontextmanager
    async def connect_stream_orders(self):
        async def inner():
            for order in self.orders:
                yield order

        yield inner()

    async def place_order(self, *args, **kwargs):
        pass

    async def cancel_order(self, *args, **kwargs):
        pass


class Informant:
    def __init__(self, fees, filters, candles):
        self.fees = fees
        self.filters = filters
        self.candles = candles

    def get_fees(self, exchange, symbol):
        return self.fees

    def get_filters(self, exchange, symbol):
        return self.filters

    async def stream_candles(self, exchange, symbol, interval, start, end):
        for candle in self.candles:
            yield candle


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
            self._remove_from_orderbook(exchange, symbol, Side.BID, fills)
        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    async def sell(self, exchange, symbol, base, test):
        fills = super().find_order_bids(exchange=exchange, symbol=symbol, base=base)
        if self._update_orderbook:
            self._remove_from_orderbook(exchange, symbol, Side.ASK, fills)
        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    def _remove_from_orderbook(self, exchange, symbol, side, fills):
        orderbook_side = self._orderbook._data[exchange][symbol][side]
        for fill in fills:
            orderbook_side[fill.price] -= fill.size
            if orderbook_side[fill.price] == Decimal(0):
                del orderbook_side[fill.price]


def Time():
    time = -1

    def get_time():
        nonlocal time
        time += 1
        return time

    return get_time
