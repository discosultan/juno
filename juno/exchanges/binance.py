from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import urllib.parse
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator, Awaitable, Dict, List, Optional, Tuple

import aiohttp
import simplejson as json

from juno import (Balance, Candle, Fees, Fill, Fills, OrderResult, OrderStatus, OrderType,
                  Side, TimeInForce, Trade)
from juno.filters import Filters, MinNotional, Price, PercentPrice, Size
from juno.http import ClientSession
from juno.math import floor_multiple
from juno.time import HOUR_MS, MIN_MS, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import Event, LeakyBucket, page, retry_on

from .exchange import Exchange

_BASE_REST_URL = 'https://api.binance.com'
_BASE_WS_URL = 'wss://stream.binance.com:9443'

_SEC_NONE = 0  # Endpoint can be accessed freely.
_SEC_TRADE = 1  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_DATA = 2  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_STREAM = 3  # Endpoint requires sending a valid API-Key.
_SEC_MARKET_DATA = 4  # Endpoint requires sending a valid API-Key.

_log = logging.getLogger(__name__)


class Binance(Exchange):

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
        self._sync_clock_task: Optional[asyncio.Task[None]] = None

        # User data stream.
        self._listen_key_refresh_task: Optional[asyncio.Task[None]] = None
        self._stream_user_data_task: Optional[asyncio.Task[None]] = None
        self._balance_event: Event[Dict[str, Balance]] = Event()
        self._order_event: Event[Any] = Event()

        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(*(_finalize_task(t) for t in (
            self._sync_clock_task, self._listen_key_refresh_task, self._stream_user_data_task)))
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_fees(self) -> Dict[str, Fees]:
        res = await self._request('GET', '/wapi/v3/tradeFee.html', security=_SEC_USER_DATA)
        return {_from_symbol(fee['symbol']): Fees(maker=fee['maker'], taker=fee['taker'])
                for fee in res['tradeFee']}

    async def map_filters(self) -> Dict[str, Filters]:
        res = await self._request('GET', '/api/v1/exchangeInfo')
        result = {}
        for symbol in res['symbols']:
            for f in symbol['filters']:
                t = f['filterType']
                if t == 'PRICE_FILTER':
                    price = f
                elif t == 'PERCENT_PRICE':
                    percent_price = f
                elif t == 'LOT_SIZE':
                    lot_size = f
                elif t == 'MIN_NOTIONAL':
                    min_notional = f
            assert all((price, percent_price, lot_size, min_notional))

            result[f"{symbol['baseAsset'].lower()}-{symbol['quoteAsset'].lower()}"] = Filters(
                price=Price(
                    min=Decimal(price['minPrice']),
                    max=Decimal(price['maxPrice']),
                    step=Decimal(price['tickSize'])),
                percent_price=PercentPrice(
                    multiplier_up=Decimal(percent_price['multiplierUp']),
                    multiplier_down=Decimal(percent_price['multiplierDown']),
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS),
                size=Size(
                    min=Decimal(lot_size['minQty']),
                    max=Decimal(lot_size['maxQty']),
                    step=Decimal(lot_size['stepSize'])),
                min_notional=MinNotional(
                    min_notional=Decimal(min_notional['minNotional']),
                    apply_to_market=min_notional['applyToMarket'],
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS))
        return result

    async def stream_balances(self) -> AsyncIterable[Dict[str, Balance]]:
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

    async def stream_depth(self, symbol: str) -> AsyncIterable[Any]:
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
            is_first_ws_message = True
            async for msg in ws:
                data = json.loads(msg.data)

                if data['u'] <= last_update_id:
                    continue

                if is_first_ws_message:
                    assert data['U'] <= last_update_id + 1 and data['u'] >= last_update_id + 1
                    is_first_ws_message = False
                else:
                    assert data['U'] == last_update_id + 1

                yield {
                    'type': 'update',
                    'bids': [(Decimal(m[0]), Decimal(m[1])) for m in data['b']],
                    'asks': [(Decimal(m[0]), Decimal(m[1])) for m in data['a']]
                }
                last_update_id = data['u']

    async def stream_orders(self) -> AsyncIterable[Any]:
        await self._ensure_user_data_stream()
        while True:
            data = await self._order_event.wait()
            self._order_event.clear()
            result = {
                'symbol': _from_symbol(data['s']),
                'status': data['x'],
                'order_status': _from_order_status(data['X']),
                'order_client_id': data['c'],
                # 'size': Decimal(data['q']),
                'fill_price': Decimal(data['L']),
                'fill_size': Decimal(data['l']),
                'fee': Decimal(data['n']),
                'fee_asset': data['N'].lower()
            }
            yield result

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

                        data = json.loads(msg.data)

                        # The data can come out of sync. Make sure to discard old updates.
                        if data['e'] == 'outboundAccountInfo' and data['E'] >= bal_time:
                            bal_time = data['E']
                            self._balance_event.set(data)
                        elif data['e'] == 'executionReport' and data['E'] >= order_time:
                            order_time = data['E']
                            self._order_event.set(data)

                        if time_ms() > valid_until:
                            _log.info('restarting user data ws connection after '
                                      f'{KEEP_ALIVE_HOURS}h')
                            break
        except asyncio.CancelledError:
            _log.info('user data streaming task cancelled')

    async def place_order(
            self,
            symbol: str,
            side: Side,
            type_: OrderType,
            size: Decimal,
            price: Optional[Decimal] = None,
            time_in_force: Optional[TimeInForce] = None,
            client_id: Optional[str] = None,
            test: bool = True) -> OrderResult:
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
        if client_id is not None:
            data['newClientOrderId'] = client_id
        url = f'/api/v3/order{"/test" if test else ""}'
        res = await self._request('POST', url, data=data, security=_SEC_TRADE)
        if test:
            return OrderResult.not_placed()
        return OrderResult(
            status=_from_order_status(res['status']),
            fills=Fills([
                Fill(
                    price=Decimal(f['price']),
                    size=Decimal(f['qty']),
                    fee=Decimal(f['commission']),
                    fee_asset=f['commissionAsset'].lower()
                ) for f in res['fills']
            ]))

    async def cancel_order(self, symbol: str, client_id: str) -> Any:
        data = {
            'symbol': _http_symbol(symbol),
            'origClientOrderId': client_id
        }
        res = await self._request('DELETE', '/api/v3/order', data=data, security=_SEC_TRADE)
        return res

    async def get_trades(self, symbol: str) -> List[Trade]:
        url = f'/api/v3/myTrades?symbol={_http_symbol(symbol)}'
        result = await self._request('GET', url, 5)
        return [Trade(x['price'], x['qty'], x['commission'], x['commissionAsset'], x['isBuyer'])
                for x in result]

    # TODO: Make sure we don't miss a candle when switching from historical to future.
    async def stream_candles(self, symbol: str, interval: int, start: int, end: int
                             ) -> AsyncIterable[Tuple[Candle, bool]]:
        current = floor_multiple(time_ms(), interval)
        if start < current:
            async for candle, primary in self._stream_historical_candles(symbol, interval, start,
                                                                         min(end, current)):
                yield candle, primary
        if end > current:
            async for candle, primary in self._stream_future_candles(symbol, interval, end):
                yield candle, primary

    async def _stream_historical_candles(self, symbol: str, interval: int, start: int, end: int
                                         ) -> AsyncIterable[Tuple[Candle, bool]]:
        MAX_CANDLES_PER_REQUEST = 1000
        for page_start, page_end in page(start, end, interval, MAX_CANDLES_PER_REQUEST):
            res = await self._request('GET', '/api/v1/klines', data={
                'symbol': _http_symbol(symbol),
                'interval': _interval(interval),
                'startTime': page_start,
                'endTime': page_end - 1,
                'limit': MAX_CANDLES_PER_REQUEST
            })
            for c in res:
                yield (Candle(c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
                       Decimal(c[5])), True)

    async def _stream_future_candles(self, symbol: str, interval: int, end: int
                                     ) -> AsyncIterable[Tuple[Candle, bool]]:
        # Binance disconnects a websocket connection every 24h. Therefore, we reconnect every 12h.
        # Note that two streams will send events with matching evt_times.
        # This can be used to switch from one stream to another and avoiding the edge case where
        # we miss out on the very last update to a candle.

        url = f'/ws/{_ws_symbol(symbol)}@kline_{_interval(interval)}'
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

                    data = json.loads(msg.data)

                    cd = data['k']
                    c = Candle(cd['t'], Decimal(cd['o']), Decimal(cd['h']), Decimal(cd['l']),
                               Decimal(cd['c']), Decimal(cd['v']))

                    # A closed candle is the last candle in a period.
                    is_closed = cd['x']
                    yield c, is_closed

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

    @retry_on(aiohttp.ClientConnectionError, max_tries=3)
    async def _request(self, method: str, url: str, weight: int = 1, data: Optional[Any] = None,
                       security: int = _SEC_NONE) -> Any:
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
            query_str_bytes = urllib.parse.urlencode(data).encode('utf-8')
            signature = hmac.new(self._secret_key_bytes, query_str_bytes, hashlib.sha256)
            data['signature'] = signature.hexdigest()

        if data:
            kwargs['params' if method == 'GET' else 'data'] = data

        async with self._session.request(method, _BASE_REST_URL + url, **kwargs) as res:
            return await res.json(loads=lambda x: json.loads(x, use_decimal=True))

    @asynccontextmanager
    # TODO: Figure out how to backoff an asynccontextmanager.
    # @retry_on(aiohttp.WSServerHandshakeError, max_tries=3)
    async def _ws_connect(self, url: str, **kwargs: Any) -> AsyncIterator[Any]:
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


def _from_symbol(symbol: str) -> str:
    # TODO: May be incorrect! We can't systematically know which part is base and which is quote
    # since there is no separator used. We simply map based on known base currencies.
    known_base_assets = ['BNB', 'BTC', 'ETH', 'XRP', 'USDT', 'PAX', 'TUSD', 'USDC', 'USDS']
    for known_base_asset in known_base_assets:
        if symbol.endswith(known_base_asset):
            quote = symbol[:-len(known_base_asset)]
            base = known_base_asset
            break
    else:
        _log.warning(f'unknown base asset found: {symbol}')
        # We round up because usually quote asset is the longer one (i.e IOTABTC).
        split_index = math.ceil(len(symbol) / 2)
        quote = symbol[:split_index]
        base = symbol[split_index:]
    return f'{quote.lower()}-{base.lower()}'


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


def _from_order_status(status: str) -> OrderStatus:
    if status == 'NEW':
        return OrderStatus.NEW
    if status == 'PARTIALLY_FILLED':
        return OrderStatus.PARTIALLY_FILLED
    if status == 'FILLED':
        return OrderStatus.FILLED
    raise NotImplementedError(f'Handling of status {status} not implemented')


def _finalize_task(task: Optional[asyncio.Task[None]]) -> Awaitable[None]:
    if task:
        task.cancel()
        return task
    res: asyncio.Future[None] = asyncio.Future()
    res.set_result(None)
    return res
