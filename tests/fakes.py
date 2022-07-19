import asyncio
from collections import defaultdict

from juno import AssetInfo, BorrowInfo, Candle, Fees, Filters, components, storages


class Chandler(components.Chandler):
    def __init__(
        self,
        candles={},
        future_candles={},
        first_candle=Candle(),
        last_candle=Candle(),
        candle_intervals=[],
    ):
        self.candles = candles
        self.future_candle_queues = defaultdict(asyncio.Queue)
        for k, cl in future_candles.items():
            future_candle_queue = self.future_candle_queues[k]
            for c in cl:
                future_candle_queue.put_nowait(c)
        self.first_candle = first_candle
        self.last_candle = last_candle
        self.candle_intervals = candle_intervals

    async def stream_candles(
        self,
        exchange,
        symbol,
        interval,
        start,
        end,
        fill_missing_with_last=False,
        simulate_open_from_interval=None,
        exchange_timeout=None,
        type_="regular",
    ):
        # TODO: Get rid of this!
        if candles := self.candles.get((exchange, symbol, interval)):
            last_candle = None
            for candle in (c for c in candles if c.time >= start and c.time < end):
                time_diff = candle.time - last_candle.time if last_candle else 0
                if time_diff >= interval * 2:
                    num_missed = time_diff // interval - 1
                    if fill_missing_with_last:
                        for i in range(1, num_missed + 1):
                            yield Candle(
                                time=last_candle.time + i * interval,
                                open=last_candle.open,
                                high=last_candle.high,
                                low=last_candle.low,
                                close=last_candle.close,
                                volume=last_candle.volume,
                            )
                yield candle
                last_candle = candle

        if future_candles := self.future_candle_queues.get((exchange, symbol, interval)):
            while True:
                candle = await future_candles.get()
                future_candles.task_done()
                yield candle
                if candle.time >= end - interval:
                    break

    async def get_first_candle(self, exchange, symbol, interval):
        return self.first_candle

    async def get_last_candle(self, exchange, symbol, interval):
        return self.last_candle

    def list_candle_intervals(self, exchange, patterns=None):
        return self.candle_intervals

    def get_interval_offset(self, exchange, interval):
        return 0


class Informant(components.Informant):
    def __init__(
        self,
        fees=Fees(),
        filters=Filters(),
        symbols=[],
        tickers={},
        exchanges=[],
        borrow_info=BorrowInfo(),
        margin_multiplier=2,
        assets=[],
        asset_info=AssetInfo(),
    ):
        self.fees = fees
        self.filters = filters
        self.symbols = symbols
        self.tickers = tickers
        self.exchanges = exchanges
        self.borrow_info = borrow_info
        self.margin_multiplier = margin_multiplier
        self.assets = assets
        self.asset_info = asset_info

    def get_asset_info(self, exchange, asset):
        return self.asset_info

    def get_borrow_info(self, account, exchange, asset):
        return self.borrow_info

    def get_margin_multiplier(self, exchange):
        return self.margin_multiplier

    def get_fees_filters(self, exchange, symbol):
        return self.fees, self.filters

    def list_symbols(
        self, exchange, patterns=None, spot=True, cross_margin=False, isolated_margin=False
    ):
        return self.symbols

    def map_tickers(
        self,
        exchange,
        symbol_patterns=None,
        exclude_symbol_patterns=None,
        spot=True,
        cross_margin=False,
        isolated_margin=False,
    ):
        return self.tickers

    def list_exchanges(self, exchange, symbol=None):
        return self.exchanges


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
        self.store_time_series_and_span_calls = []
        self.get_calls = []
        self.set_calls = []

    async def store_time_series_and_span(self, shard, key, items, start, end):
        await super().store_time_series_and_span(shard, key, items, start, end)
        self.store_time_series_and_span_calls.append((shard, key, items, start, end))
        self.stored_time_series_and_span.set()
        await asyncio.sleep(0)

    async def get(self, shard, key, type_):
        result = await super().get(shard, key, type_)
        self.get_calls.append((shard, key, type_, result))
        return result

    async def set(self, shard, key, item):
        await super().set(shard, key, item)
        self.set_calls.append((shard, key, item, None))
