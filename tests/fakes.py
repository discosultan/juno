import asyncio
from contextlib import asynccontextmanager

from juno import (
    CancelOrderResult, CancelOrderStatus, Fees, Filters, OrderResult, OrderStatus, Side,
    SymbolsInfo, brokers, components, exchanges
)


class Exchange(exchanges.Exchange):
    def __init__(
        self,
        historical_candles=[],
        future_candles=[],
        symbol_info=SymbolsInfo(
            fees={'__all__': Fees.none()}, filters={'__all__': Filters.none()}
        ),
        balances=None,
        future_balances=[],
        depth=None,
        future_depths=[],
        future_orders=[],
        place_order_result=OrderResult(status=OrderStatus.NEW),
        cancel_order_result=CancelOrderResult(status=CancelOrderStatus.SUCCESS),
    ):
        super().__init__()

        self.historical_candles = historical_candles
        self.candle_queue = asyncio.Queue()
        for future_candle in future_candles:
            self.candle_queue.put_nowait(future_candle)

        self.symbol_info = symbol_info

        self.balances = balances
        self.balance_queue = asyncio.Queue
        for future_balance in future_balances:
            self.balance_queue.put_nowait(future_balance)

        self.depth = depth
        self.depth_queue = asyncio.Queue()
        for future_depth in future_depths:
            self.depth_queue.put_nowait(future_depth)

        self.orders_queue = asyncio.Queue()
        for future_order in future_orders:
            self.orders_queue.put_nowait(future_order)

        self.place_order_result = place_order_result
        self.place_order_calls = []

        self.cancel_order_result = cancel_order_result
        self.cancel_order_calls = []

    async def get_symbols_info(self):
        return self.symbol_info

    async def get_balances(self):
        return self.balances

    @asynccontextmanager
    async def connect_stream_balances(self):
        async def inner():
            while True:
                yield await self.balance_queue.get()

        yield inner()

    async def stream_historical_candles(self, symbol, interval, start, end):
        for c in (c for c in self.historical_candles if c.time >= start and c.time < end):
            yield c

    @asynccontextmanager
    async def connect_stream_candles(self, symbol, interval):
        async def inner():
            while True:
                yield await self.candle_queue.get()

        yield inner()

    async def get_depth(self, symbol):
        return self.depth

    @asynccontextmanager
    async def connect_stream_depth(self, symbol):
        async def inner():
            while True:
                yield await self.depth_queue.get()

        yield inner()

    @asynccontextmanager
    async def connect_stream_orders(self):
        async def inner():
            while True:
                yield await self.orders_queue.get()

        yield inner()

    async def place_order(self, *args, **kwargs):
        await asyncio.sleep(0)
        # TODO: We are ignore *args
        self.place_order_calls.append({**kwargs})
        return self.place_order_result

    async def cancel_order(self, *args, **kwargs):
        await asyncio.sleep(0)
        self.cancel_order_calls.append({**kwargs})
        return self.cancel_order_result


class Chandler:
    def __init__(self, candles):
        self.candles = candles

    async def stream_candles(self, exchange, symbol, interval, start, end):
        for c in (c for c in self.candles if c.time >= start and c.time < end):
            yield c


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
            if orderbook_side[fill.price] == 0:
                del orderbook_side[fill.price]


class Strategy:
    def __init__(self, *advices):
        self.advices = list(reversed(advices))
        self.updates = []

    def update(self, candle):
        self.updates.append(candle)
        return self.advices.pop()


def Time():
    time = -1

    def get_time():
        nonlocal time
        time += 1
        return time

    return get_time
