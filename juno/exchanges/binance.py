import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import logging
import json

import aiohttp
import backoff

from juno import AccountInfo, BidAsk, Candle, Depth, Fees, OrderResult, SymbolInfo, Trade
from juno.http import ClientSession
from juno.math import floor_multiple
from juno.utils import LeakyBucket, page
from juno.time import HOUR_MS, time_ms


_BASE_URL = 'https://api.binance.com'

_log = logging.getLogger(__package__)


class Binance:

    def __init__(self, api_key: str, secret_key: str):
        self._session = None
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')

        # Rate limiters.
        self._reqs_per_min_limiter = LeakyBucket(rate=1200, period=60)           # 1200 per min.
        self._orders_per_sec_limiter = LeakyBucket(rate=10, period=1)            # 10 per sec.
        self._orders_per_day_limiter = LeakyBucket(rate=100_000, period=86_400)  # 100 000 per day.

        # Clock synchronization.
        self._time_diff = 0
        self._sync_clock = None

    async def __aenter__(self):
        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_symbol_infos(self):
        res = await self._request('GET', '/api/v1/exchangeInfo', 1)
        result = {}
        for symbol in res['symbols']:
            size = next((f for f in symbol['filters'] if f['filterType'] == 'LOT_SIZE'))
            price = next((f for f in symbol['filters'] if f['filterType'] == 'PRICE_FILTER'))
            result[f"{symbol['baseAsset']}-{symbol['quoteAsset']}"] = SymbolInfo(
                min_size=float(size['minQty']),
                max_size=float(size['maxQty']),
                size_step=float(size['stepSize']),
                min_price=float(price['minPrice']),
                max_price=float(price['maxPrice']),
                price_step=float(price['tickSize']))
        return result

    async def get_account_info(self, symbol):
        base, quote = (asset.upper() for asset in symbol.split('-'))

        url = '/api/v3/account?'
        res = await self._order('GET', url, 5)
        balances = res['balances']

        base_balance = float(next(b for b in balances if b['asset'] == base)['free'])
        quote_balance = float(next(b for b in balances if b['asset'] == quote)['free'])

        return AccountInfo(time_ms(), base_balance, quote_balance,
                           Fees(res['makerCommission'] / 10000.0,
                           res['takerCommission'] / 10000.0))

    async def place_order(self, symbol, side, type_, qty, price, time_in_force, test=False):
        url = (f'/api/v3/order{"/test" if test else ""}'
               f'?symbol={_http_symbol(symbol)}'
               f'&side={side.name}'
               f'&type={type_.name}'
               f'&quantity={qty}')
        if price is not None:
            url += f'&price={price}'
        if time_in_force is not None:
            url += f'&timeInForce={time_in_force.name}'
        res = await self._order('POST', url, 1)
        return OrderResult(res['price'], res['executedQty'])

    async def get_depth(self, symbol):
        url = f'/api/v1/depth?limit=100&symbol={_http_symbol(symbol)}'
        result = await self._request('GET', url, 1)
        return Depth(
            [BidAsk(float(x[0]), float(x[1])) for x in result['bids']],
            [BidAsk(float(x[0]), float(x[1])) for x in result['asks']])

    async def get_trades(self, symbol):
        url = f'/api/v3/myTrades?symbol={_http_symbol(symbol)}'
        result = await self._order('GET', url, 5)
        return [Trade(x['price'], x['qty'], x['commission'], x['commissionAsset'], x['isBuyer'])
                for x in result]

    # TODO: Make sure we don't miss a candle when switching from historical to future.
    async def stream_candles(self, symbol, interval, start, end):
        current = floor_multiple(time_ms(), interval)
        if start < current:
            async for candle, primary in self._stream_historical_candles(symbol, interval, start,
                                                                         min(end, current)):
                yield candle, primary
        if end > current:
            async for candle, primary in self._stream_future_candles(symbol, interval, end):
                yield candle, primary

    async def _stream_historical_candles(self, symbol, interval, start, end):
        MAX_CANDLES_PER_REQUEST = 1000
        for page_start, page_end in page(start, end, interval, MAX_CANDLES_PER_REQUEST):
            url = (f'/api/v1/klines'
                   f'?symbol={_http_symbol(symbol)}'
                   f'&interval={_interval(interval)}'
                   f'&startTime={page_start}'
                   f'&endTime={page_end - 1}')
            res = await self._request('GET', url, 1)
            for c in res:
                yield (Candle(c[0], float(c[1]), float(c[2]), float(c[3]), float(c[4]),
                       float(c[5])), True)

    async def _stream_future_candles(self, symbol, interval, end):
        # Binance disconnects a websocket connection every 24h. Therefore, we reconnect every 12h.
        # Note that two streams will send events with matching evt_times.
        # This can be used to switch from one stream to another and avoiding the edge case where
        # we miss out on the very last update to a candle.

        url = f'wss://stream.binance.com:9443/ws/{_ws_symbol(symbol)}@kline_{_interval(interval)}'
        last_candle = None
        while True:
            stream_start = time_ms()
            if stream_start >= end:
                break

            valid_until = stream_start + HOUR_MS * 12

            async with self._ws_connect(url) as ws:
                async for msg in ws:
                    _log.debug(msg)

                    if msg.type is aiohttp.WSMsgType.CLOSED:
                        _log.error(f'binance ws connection closed unexpectedly ({msg})')
                        break

                    c = json.loads(msg.data)['k']
                    c = Candle(c['t'], float(c['o']), float(c['h']), float(c['l']), float(c['c']),
                               float(c['v']))

                    # Since updates are given every second, we are only interested in the last
                    # update for any particular candle. We keep track of two consecutive candles to
                    # find the last one for a period. Note that:
                    #  * we can receive more than one update within a second
                    #  * event time can be later than candle close time
                    if last_candle is not None and c.time > last_candle.time:
                        yield c, True
                    else:
                        yield c, False

                    last_candle = c
                    if c.time >= end - interval:
                        return
                    if time_ms() > valid_until:
                        break

    @backoff.on_exception(backoff.expo, (aiohttp.ClientError, asyncio.TimeoutError), max_tries=5)
    async def _request(self, method, url, cost):
        await self._reqs_per_min_limiter.acquire(cost)
        async with self._session.request(method, _BASE_URL + url) as res:
            return await res.json()

    @backoff.on_exception(backoff.expo, (aiohttp.ClientError, asyncio.TimeoutError), max_tries=3)
    async def _order(self, method, url, cost):
        # Synchronize clock. Note that we may want to do this periodically instead of only
        # initially.
        if self._sync_clock is None:
            self._sync_clock = asyncio.get_running_loop().create_task(self._ensure_clock_synced())
        await self._sync_clock

        await asyncio.gather(
            self._orders_per_day_limiter.acquire(cost),
            self._orders_per_sec_limiter.acquire(cost))

        # Add timestamp.
        url += f'&timestamp={time_ms() + self._time_diff}'
        # Add signature query param.
        query_str = url[url.find('?') + 1:].encode('utf-8')
        m = hmac.new(self._secret_key_bytes, query_str, hashlib.sha256)
        url += f'&signature={m.hexdigest()}'
        # Add API key header.
        headers = {'X-MBX-APIKEY': self._api_key}
        async with self._session.request(method, _BASE_URL + url, headers=headers) as res:
            return await res.json()

    @asynccontextmanager
    @backoff.on_exception(backoff.expo, aiohttp.WSServerHandshakeError, max_tries=5)
    async def _ws_connect(self, url, **kwargs):
        async with self._session.ws_connect(url, **kwargs) as ws:
            yield ws

    async def _ensure_clock_synced(self):
        before = time_ms()
        server_time = (await self._request('GET', '/api/v1/time', 1))['serverTime']
        after = time_ms()
        # Assume response time is same as request time.
        delay = (after - before) // 2
        self._time_diff = server_time - after - delay
        # TODO: If we want to sync periodically, we should schedule a task on the event loop
        # to set self.sync_clock to None after a period of time. This will force re-sync.
        # We can schedule a task using loop.create_task. Note that we must also cancel the
        # task if the event loop ends before the task is finished. Otherwise, we will get a
        # warning.


def _http_symbol(symbol):
    return symbol.replace('-', '').upper()


def _ws_symbol(symbol):
    return symbol.replace('-', '')


def _interval(interval):
    return {
        1000: '1s',
        60_000: '1m',
        180_000: '3m',
        300_000: '5m',
        900_000: '15m',
        1_800_000: '30m',
        3_600_000: '1h',
        7_200_000: '2h',
        14_400_000: '4h',
        21_600_000: '6h',
        28_800_000: '8h',
        43_200_000: '12h',
        86_400_000: '1d',
        259_200_000: '3d',
        604_800_000: '1w',
        2_629_746_000: '1M',
    }[interval]
