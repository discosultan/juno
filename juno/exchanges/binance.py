from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional

import aiohttp
import backoff
import simplejson as json

from juno import Balance, Candle, OrderResult, SymbolInfo, Trade
from juno.http import ClientSession
from juno.math import floor_multiple
from juno.utils import LeakyBucket, page, Event
from juno.time import HOUR_MS, MIN_MS, time_ms


_BASE_REST_URL = 'https://api.binance.com'
_BASE_WS_URL = 'wss://stream.binance.com:9443'

_SEC_NONE = 0  # Endpoint can be accessed freely.
_SEC_TRADE = 1  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_DATA = 2  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_STREAM = 3  # Endpoint requires sending a valid API-Key.
_SEC_MARKET_DATA = 4  # Endpoint requires sending a valid API-Key.

_log = logging.getLogger(__name__)


class Binance:

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')

    async def __aenter__(self) -> Binance:
        # Rate limiters.
        self._reqs_per_min_limiter = LeakyBucket(rate=1200, period=60)           # 1200 per min.
        self._orders_per_sec_limiter = LeakyBucket(rate=10, period=1)            # 10 per sec.
        self._orders_per_day_limiter = LeakyBucket(rate=100_000, period=86_400)  # 100 000 per day.

        # Clock synchronization.
        self._time_diff = 0
        self._sync_clock_task = None

        # User data stream.
        self._listen_key_refresh_task: Optional[asyncio.Task[None]] = None
        self._stream_user_data_task: Optional[asyncio.Task[None]] = None
        self._balance_event = Event()
        self._order_event = Event()

        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._listen_key_refresh_task and self._stream_user_data_task:
            self._listen_key_refresh_task.cancel()
            self._stream_user_data_task.cancel()
            await asyncio.gather(self._stream_user_data_task, self._listen_key_refresh_task)
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_symbol_infos(self) -> Dict[str, SymbolInfo]:
        res = await self._request('GET', '/api/v1/exchangeInfo')
        result = {}
        for symbol in res['symbols']:
            size = next((f for f in symbol['filters'] if f['filterType'] == 'LOT_SIZE'))
            price = next((f for f in symbol['filters'] if f['filterType'] == 'PRICE_FILTER'))
            result[f"{symbol['baseAsset']}-{symbol['quoteAsset']}"] = SymbolInfo(
                min_size=Decimal(size['minQty']),
                max_size=Decimal(size['maxQty']),
                size_step=Decimal(size['stepSize']),
                min_price=Decimal(price['minPrice']),
                max_price=Decimal(price['maxPrice']),
                price_step=Decimal(price['tickSize']))
        return result

    async def stream_balances(self):
        # Get initial status from REST API.
        res = await self._request('GET', '/api/v3/account', weight=5, security=_SEC_USER_DATA)
        result = {}
        for balance in res['balances']:
            result[balance['asset'].lower()] = Balance(
                available=Decimal(balance['free']),
                hold=Decimal(balance['locked']))
        yield result

        # Stream future updates over WS.
        await self._ensure_user_data_stream()
        while True:
            data = await self._balance_event.wait()
            self._balance_event.clear()
            result = {}
            for balance in data['B']:
                result[balance['a'].lower()] = Balance(
                    available=Decimal(balance['f']),
                    hold=Decimal(balance['l']))
            yield result

    async def stream_depth(self, symbol):
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#diff-depth-stream
        async with self._ws_connect(f'/ws/{_ws_symbol(symbol)}@depth') as ws:
            # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#market-data-endpoints
            result = await self._request('GET', '/api/v1/depth', data={
                'limit': 100,  # TODO: We might wanna increase that and accept higher weight.
                'symbol': _http_symbol(symbol)
            })
            yield {
                'type': 'snapshot',
                'bids': [(Decimal(x[0]), Decimal(x[1])) for x in result['bids']],
                'asks': [(Decimal(x[0]), Decimal(x[1])) for x in result['asks']]
            }
            last_update_id = result['lastUpdateId']
            async for msg in ws:
                if msg['u'] <= last_update_id:
                    continue

                assert msg['U'] <= last_update_id + 1 and msg['u'] >= last_update_id + 1
                assert msg['u'] == last_update_id + 1

                yield {
                    'type': 'update',
                    'bids': [(Decimal(m[0]), Decimal(m[1])) for m in msg['b']],
                    'asks': [(Decimal(m[0]), Decimal(m[1])) for m in msg['a']]
                }
                last_update_id = msg['u']

    async def stream_orders(self):
        await self._ensure_user_data_stream()
        while True:
            yield True
            # _data = await self._order_event.wait()
            # self._order_event.clear()
            # result = {}
            # for balance in data['B']:
            #     result[balance['a'].lower()] = Balance(
            #         available=Decimal(balance['f']),
            #         hold=Decimal(balance['l']))
            # yield result

    async def _ensure_user_data_stream(self) -> None:
        if self._listen_key_refresh_task:
            return

        listen_key = (await self._request(
            'POST',
            '/api/v1/userDataStream',
            security=_SEC_USER_STREAM))['listenKey']
        self._listen_key_refresh_task = asyncio.create_task(
            self._periodic_listen_key_refresh(listen_key))
        self._stream_user_data_task = asyncio.create_task(
            self._stream_user_data(listen_key))

    async def _stream_user_data(self, listen_key: str) -> None:
        try:
            bal_time, order_time = 0, 0
            while True:
                KEEP_ALIVE_HOURS = 12
                valid_until = time_ms() + KEEP_ALIVE_HOURS * HOUR_MS

                async with self._ws_connect('/ws/' + listen_key) as ws:
                    async for msg in ws:
                        if msg.type is aiohttp.WSMsgType.CLOSED:
                            _log.error(f'user data ws connection closed unexpectedly ({msg})')

                        # The data can come out of sync. Make sure to discard old updates.
                        if msg.data['e'] == 'outboundAccountInfo' and msg.data['E'] >= bal_time:
                            bal_time = msg.data['E']
                            self._balance_event.set(msg.data)
                        elif msg.data['e'] == 'executionReport' and msg.data['E'] >= order_time:
                            order_time = msg.data['E']
                            self._order_event.set(msg.data)

                        if time_ms() > valid_until:
                            _log.info('restarting user data ws connection after '
                                      f'{KEEP_ALIVE_HOURS}h')
                            break
        except asyncio.CancelledError:
            _log.info('user data streaming task cancelled')

    async def place_order(self, symbol, side, type_, size, price, time_in_force, test=False):
        data = {
            'symbol': _http_symbol(symbol),
            'side': side.name,
            'type': type_.name,
            'quantity': str(size)
        }
        if price is not None:
            data['price'] = str(price)
        if time_in_force is not None:
            data['timeInForce'] = time_in_force.name
        url = f'/api/v3/order{"/test" if test else ""}'
        res = await self._request('POST', url, data=data)
        return OrderResult(res['price'], res['executedQty'])

    async def get_trades(self, symbol: str) -> List[Trade]:
        url = f'/api/v3/myTrades?symbol={_http_symbol(symbol)}'
        result = await self._request('GET', url, 5)
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
            res = await self._request('GET', '/api/v1/klines', data={
                'symbol': _http_symbol(symbol),
                'interval': _interval(interval),
                'startTime': page_start,
                'endTime': page_end - 1
            })
            for c in res:
                yield (Candle(c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
                       Decimal(c[5])), True)

    async def _stream_future_candles(self, symbol, interval, end):
        # Binance disconnects a websocket connection every 24h. Therefore, we reconnect every 12h.
        # Note that two streams will send events with matching evt_times.
        # This can be used to switch from one stream to another and avoiding the edge case where
        # we miss out on the very last update to a candle.

        url = f'/ws/{_ws_symbol(symbol)}@kline_{_interval(interval)}'
        last_candle = None
        while True:
            stream_start = time_ms()
            valid_until = stream_start + HOUR_MS * 12

            if stream_start >= end:
                break

            async with self._ws_connect(url) as ws:
                async for msg in ws:
                    if msg.type is aiohttp.WSMsgType.CLOSED:
                        _log.error(f'candles ws connection closed unexpectedly ({msg})')
                        break

                    c = json.loads(msg.data)['k']
                    c = Candle(c['t'], Decimal(c['o']), Decimal(c['h']), Decimal(c['l']),
                               Decimal(c['c']), Decimal(c['v']))

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

    async def _periodic_listen_key_refresh(self, listen_key: str) -> None:
        try:
            while True:
                await asyncio.sleep(MIN_MS * 30)
                await self._request(
                    'PUT',
                    '/api/v1/userDataStream',
                    data={'listenKey': listen_key},
                    security=_SEC_USER_STREAM)
        except asyncio.CancelledError:
            _log.info('periodic listen key refresh task cancelled')
        finally:
            await self._request(
                'DELETE',
                '/api/v1/userDataStream',
                data={'listenKey': listen_key},
                security=_SEC_USER_STREAM)

    @backoff.on_exception(backoff.expo, aiohttp.ClientConnectionError, max_tries=3)
    async def _request(self, method, url, weight=1, data=None, security=_SEC_NONE):
        if method == '/api/v3/order':
            await asyncio.gather(
                self._reqs_per_min_limiter.acquire(weight),
                self._orders_per_day_limiter.acquire(),
                self._orders_per_sec_limiter.acquire())
        else:
            await self._reqs_per_min_limiter.acquire(weight)

        kwargs = {}

        if security in [_SEC_TRADE, _SEC_USER_DATA, _SEC_USER_STREAM, _SEC_MARKET_DATA]:
            kwargs['headers'] = {'X-MBX-APIKEY': self._api_key}

        if security in [_SEC_TRADE, _SEC_USER_DATA]:
            # Synchronize clock. Note that we may want to do this periodically instead of only
            # initially.
            if not self._sync_clock_task:
                self._sync_clock_task = asyncio.create_task(self._sync_clock())
            await self._sync_clock_task

            data = data or {}
            data['timestamp'] = time_ms() + self._time_diff
            query_str_bytes = _query_string(data).encode('utf-8')
            signature = hmac.new(self._secret_key_bytes, query_str_bytes, hashlib.sha256)
            data['signature'] = signature.hexdigest()

        if data:
            kwargs['params' if method == 'GET' else 'data'] = data

        async with self._session.request(method, _BASE_REST_URL + url, **kwargs) as res:
            return await res.json()

    @asynccontextmanager
    @backoff.on_exception(backoff.expo, aiohttp.WSServerHandshakeError, max_tries=3)
    async def _ws_connect(self, url, **kwargs):
        async with self._session.ws_connect(_BASE_WS_URL + url, **kwargs) as ws:
            yield ws

    async def _sync_clock(self) -> None:
        try:
            _log.info('syncing clock with Binance')
            before = time_ms()
            server_time = (await self._request('GET', '/api/v1/time'))['serverTime']
            after = time_ms()
            # Assume response time is same as request time.
            delay = (after - before) // 2
            self._time_diff = server_time - after - delay
            _log.info(f'found {self._time_diff}ms time difference')
            # TODO: If we want to sync periodically, we should schedule a task on the event loop
            # to set self.sync_clock to None after a period of time. This will force re-sync.
        except asyncio.CancelledError:
            _log.info('sync clock task cancelled')


def _http_symbol(symbol: str) -> str:
    return symbol.replace('-', '').upper()


def _ws_symbol(symbol: str) -> str:
    return symbol.replace('-', '')


def _interval(interval: int) -> str:
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


def _query_string(data: Dict[str, Any]) -> str:
    return '&'.join((f'{key}={value}' for key, value in data.items()))
