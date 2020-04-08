import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Dict, List, Tuple

from juno import (
    Balance, BorrowInfo, CancelOrderResult, CancelOrderStatus, Candle, ExchangeInfo, Fees, Filters,
    OrderResult, OrderStatus, Side, brokers, components, exchanges, storages
)
from juno.asyncio import Event


class Exchange(exchanges.Exchange):
    can_stream_balances: bool = True
    can_stream_depth_snapshot: bool = True
    can_stream_historical_earliest_candle: bool = True
    can_stream_historical_candles: bool = True
    can_stream_candles: bool = True
    can_list_all_tickers: bool = True
    can_margin_trade: bool = True

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
        self.get_exchange_info_calls = []
        self.tickers = tickers

        self.balances = balances
        self.balance_queue = asyncio.Queue()
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
        result = self.exchange_info
        self.get_exchange_info_calls.append([result])
        return result

    async def list_tickers(self):
        return self.tickers

    async def get_balances(self, margin=False):
        return self.balances

    @asynccontextmanager
    async def connect_stream_balances(self, margin=False):
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
    async def connect_stream_orders(self, margin=False):
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


class Chandler(components.Chandler):
    def __init__(self, candles={}, future_candles={}):
        self.candles = candles
        self.future_candle_queues = defaultdict(asyncio.Queue)
        for k, cl in future_candles.items():
            future_candle_queue = self.future_candle_queues[k]
            for c in cl:
                future_candle_queue.put_nowait(c)

    async def stream_candles(
        self, exchange, symbol, interval, start, end, closed=True, fill_missing_with_last=False
    ):
        candles = self.candles[(exchange, symbol, interval)]
        last_c = None
        for c in (c for c in candles if c.time >= start and c.time < end):
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

        # TODO: walrus
        future_candles = self.future_candle_queues.get((exchange, symbol, interval))
        if future_candles:
            while True:
                candle = await future_candles.get()
                yield candle
                future_candles.task_done()
                if candle.time >= end - interval:
                    break


class Trades(components.Trades):
    def __init__(self, trades=[]):
        self.trades = trades

    async def stream_trades(self, exchange, symbol, start, end):
        for t in (t for t in self.trades if t.time >= start and t.time < end):
            yield t


class Informant(components.Informant):
    def __init__(
        self,
        fees=Fees(),
        filters=Filters(),
        symbols=[],
        candle_intervals=[],
        tickers=[],
        exchanges=[],
        exchanges_supporting_symbol=[],
        borrow_info=(BorrowInfo(), 1),
    ):
        self.fees = fees
        self.filters = filters
        self.symbols = symbols
        self.candle_intervals = candle_intervals
        self.tickers = tickers
        self.exchanges = exchanges
        self.exchanges_supporting_symbol = exchanges_supporting_symbol
        self.borrow_info = borrow_info

    def get_borrow_info(self, exchange, asset):
        return self.borrow_info

    def get_fees_filters(self, exchange, symbol):
        return self.fees, self.filters

    def list_symbols(self, exchange, patterns=None):
        return self.symbols

    def list_candle_intervals(self, exchange, patterns=None):
        return self.candle_intervals

    def list_tickers(self, exchange):
        return self.tickers

    def list_exchanges(self, exchange):
        return self.exchanges

    def list_exchanges_supporting_symbol(self, symbol):
        return self.exchanges_supporting_symbol


class Orderbook(components.Orderbook):
    def __init__(
        self, data: Dict[str, Dict[str, Dict[Side, Dict[Decimal, Decimal]]]] = {}
    ) -> None:
        self._data_ = data

    def get_updated_event(self, exchange: str, symbol: str) -> Event[None]:
        raise NotImplementedError()

    def list_asks(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._data_[exchange][symbol][Side.BUY].items())

    def list_bids(self, exchange: str, symbol: str) -> List[Tuple[Decimal, Decimal]]:
        return sorted(self._data_[exchange][symbol][Side.SELL].items(), reverse=True)


class Wallet(components.Wallet):
    def __init__(self, data: Dict[str, Dict[str, Balance]]):
        self._data_ = data

    def get_balance(self, exchange: str, asset: str, margin: bool = False) -> Balance:
        return self._data_[exchange][asset]

    def get_updated_event(self, exchange: str, margin: bool = False) -> Event[None]:
        raise NotImplementedError()


class Market(brokers.Market):
    def __init__(self, informant, orderbook, update_orderbook):
        self._informant = informant
        self._orderbook = orderbook
        self._update_orderbook = update_orderbook

    async def buy(self, exchange, symbol, size, test):
        fills = super().find_order_asks(exchange=exchange, symbol=symbol, size=size)
        if self._update_orderbook:
            self._remove_from_orderbook(exchange, symbol, Side.BUY, fills)
        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    async def buy_by_quote(self, exchange, symbol, quote, test):
        fills = super().find_order_asks_by_quote(exchange=exchange, symbol=symbol, quote=quote)
        if self._update_orderbook:
            self._remove_from_orderbook(exchange, symbol, Side.BUY, fills)
        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    async def sell(self, exchange, symbol, size, test):
        fills = super().find_order_bids(exchange=exchange, symbol=symbol, size=size)
        if self._update_orderbook:
            self._remove_from_orderbook(exchange, symbol, Side.SELL, fills)
        return OrderResult(status=OrderStatus.FILLED, fills=fills)

    def _remove_from_orderbook(self, exchange, symbol, side, fills):
        orderbook_side = self._orderbook._data_[exchange][symbol][side]
        for fill in fills:
            orderbook_side[fill.price] -= fill.size
            if orderbook_side[fill.price] == 0:
                del orderbook_side[fill.price]


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
        self.get_calls = []
        self.set_calls = []

    async def store_time_series_and_span(self, *args, **kwargs):
        await super().store_time_series_and_span(*args, **kwargs)
        self.stored_time_series_and_span.set()
        await asyncio.sleep(0)

    async def get(self, shard, key, type_):
        result = await super().get(shard, key, type_)
        self.get_calls.append([shard, key, type_, result])
        return result

    async def set(self, shard, key, item):
        await super().set(shard, key, item)
        self.set_calls.append([shard, key, item, None])
