import asyncio
from contextlib import asynccontextmanager

from juno import (
    CancelOrderResult, CancelOrderStatus, Candle, ExchangeInfo, Fees, Filters, OrderResult,
    OrderStatus, Side, brokers, components, exchanges, storages
)
from juno.asyncio import list_async


class Exchange(exchanges.Exchange):
    can_stream_balances: bool = True
    can_stream_depth_snapshot: bool = True
    can_stream_historical_candles: bool = True
    can_stream_candles: bool = True
    can_list_24hr_tickers: bool = True

    def __init__(
        self,
        historical_candles=[],
        future_candles=[],
        exchange_info=ExchangeInfo(
            fees={'__all__': Fees()}, filters={'__all__': Filters()}
        ),
        tickers=[],
        balances=None,
        future_balances=[],
        depth=None,
        future_depths=[],
        future_orders=[],
        place_order_result=OrderResult(status=OrderStatus.NEW),
        cancel_order_result=CancelOrderResult(status=CancelOrderStatus.SUCCESS),
        historical_trades=[],
        future_trades=[],
    ):
        super().__init__()

        self.historical_candles = historical_candles
        self.candle_queue = asyncio.Queue()
        for future_candle in future_candles:
            self.candle_queue.put_nowait(future_candle)

        self.exchange_info = exchange_info
        self.tickers = tickers

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

        self.historical_trades = historical_trades
        self.trade_queue = asyncio.Queue()
        for future_trade in future_trades:
            self.trade_queue.put_nowait(future_trade)

    async def get_exchange_info(self):
        return self.exchange_info

    async def list_24hr_tickers(self):
        return self.tickers

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
                item = await self.candle_queue.get()
                self.candle_queue.task_done()
                if isinstance(item, Exception):
                    raise item
                yield item

        yield inner()

    async def get_depth(self, symbol):
        return self.depth

    @asynccontextmanager
    async def connect_stream_depth(self, symbol):
        async def inner():
            while True:
                yield await self.depth_queue.get()
                self.depth_queue.task_done()

        yield inner()

    @asynccontextmanager
    async def connect_stream_orders(self):
        async def inner():
            while True:
                yield await self.orders_queue.get()
                self.orders_queue.task_done()

        yield inner()

    async def place_order(self, *args, **kwargs):
        await asyncio.sleep(0)
        # TODO: We are ignoring *args
        self.place_order_calls.append({**kwargs})
        return self.place_order_result

    async def cancel_order(self, *args, **kwargs):
        await asyncio.sleep(0)
        self.cancel_order_calls.append({**kwargs})
        return self.cancel_order_result

    async def stream_historical_trades(self, symbol, start, end):
        for t in (t for t in self.historical_trades if t.time >= start and t.time < end):
            yield t

    @asynccontextmanager
    async def connect_stream_trades(self, symbol):
        async def inner():
            while True:
                yield await self.trade_queue.get()
                self.trade_queue.task_done()

        yield inner()


class Chandler:
    def __init__(self, candles=[]):
        self.candles = candles

    async def list_candles(self, *args, **kwargs):
        return await list_async(self.stream_candles(*args, **kwargs))

    async def stream_candles(
        self, exchange, symbol, interval, start, end, closed=True, fill_missing_with_last=False
    ):
        last_c = None
        for c in (c for c in self.candles if c.time >= start and c.time < end):
            time_diff = c.time - last_c.time if last_c else 0
            if time_diff >= interval * 2:
                num_missed = time_diff // interval - 1
                if fill_missing_with_last:
                    for i in range(1, num_missed + 1):
                        yield Candle(
                            time=last_c.time + i * interval,
                            open=last_c.open,
                            high=last_c.high,
                            low=last_c.low,
                            close=last_c.close,
                            volume=last_c.volume,
                            closed=True
                        )
            if not closed or c.closed:
                yield c
            last_c = c


class Trades:
    def __init__(self, trades=[]):
        self.trades = trades

    async def stream_trades(self, exchange, symbol, start, end):
        for t in (t for t in self.trades if t.time >= start and t.time < end):
            yield t


class Informant:
    def __init__(
        self,
        fees=Fees(),
        filters=Filters(),
        exchanges_supporting_symbol=[],
        candle_intervals=[],
        symbols=[]
    ):
        self.fees = fees
        self.filters = filters
        self.exchanges_supporting_symbol = exchanges_supporting_symbol
        self.candle_intervals = candle_intervals
        self.symbols = symbols

    def get_fees_filters(self, exchange, symbol):
        return self.fees, self.filters

    def list_exchanges_supporting_symbol(self, symbol):
        return self.exchanges_supporting_symbol

    def list_candle_intervals(self, exchange, patterns=None):
        return self.candle_intervals

    def list_symbols(self, exchange, patterns=None):
        return self.symbols


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

    @property
    def advice(self):
        return self.advices.pop()


class Time:
    def __init__(self, time=0, increment=0):
        self.time = time
        self.increment = increment

    def get_time(self):
        time = self.time
        self.time += self.increment
        return time


class Storage(storages.Memory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stored_time_series_and_span = asyncio.Event()

    async def store_time_series_and_span(self, *args, **kwargs):
        await super().store_time_series_and_span(*args, **kwargs)
        self.stored_time_series_and_span.set()
        await asyncio.sleep(0)
