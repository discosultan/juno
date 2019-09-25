from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import urllib.parse
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncContextManager, AsyncIterable, AsyncIterator, Dict, Optional

import simplejson as json

from juno import (
    Balance, CancelOrderResult, CancelOrderStatus, Candle, DepthUpdate, DepthUpdateType, Fees,
    Fill, Fills, OrderResult, OrderStatus, OrderType, OrderUpdate, Side, TimeInForce
)
from juno.asyncio import Event, cancel, cancelable
from juno.filters import Filters, MinNotional, PercentPrice, Price, Size
from juno.http import ClientSession, connect_refreshing_stream
from juno.math import floor_multiple
from juno.time import HOUR_SEC, MIN_MS, MIN_SEC, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import LeakyBucket, page

from .exchange import Exchange

_BASE_REST_URL = 'https://api.binance.com'
_BASE_WS_URL = 'wss://stream.binance.com:9443'

_SEC_NONE = 0  # Endpoint can be accessed freely.
_SEC_TRADE = 1  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_DATA = 2  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_STREAM = 3  # Endpoint requires sending a valid API-Key.
_SEC_MARKET_DATA = 4  # Endpoint requires sending a valid API-Key.

_ERR_CANCEL_REJECTED = -2011

_log = logging.getLogger(__name__)


class Binance(Exchange):
    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')

    async def __aenter__(self) -> Binance:
        # Rate limiters.
        self._reqs_per_min_limiter = LeakyBucket(rate=1200, period=60)  # 1200 per min.
        self._orders_per_sec_limiter = LeakyBucket(rate=10, period=1)  # 10 per sec.
        self._orders_per_day_limiter = LeakyBucket(rate=100_000, period=86_400)  # 100 000 per day.

        # Clock synchronization.
        self._time_diff = 0
        self._sync_clock_task: Optional[asyncio.Task[None]] = None

        # User data stream.
        self._listen_key_lock = asyncio.Lock()
        self._listen_key_refresh_task: Optional[asyncio.Task[None]] = None
        self._stream_user_data_task: Optional[asyncio.Task[None]] = None
        self._balance_event: Event[Dict[str, Balance]] = Event(autoclear=True)
        self._order_event: Event[Any] = Event(autoclear=True)

        self._session = ClientSession(raise_for_status=False)
        await self._session.__aenter__()

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(
            self._sync_clock_task, self._listen_key_refresh_task, self._stream_user_data_task
        )
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_fees(self) -> Dict[str, Fees]:
        res = await self._request('GET', '/wapi/v3/tradeFee.html', security=_SEC_USER_DATA)
        return {
            _from_symbol(fee['symbol']): Fees(maker=fee['maker'], taker=fee['taker'])
            for fee in res['tradeFee']
        }

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
                base_precision=symbol['baseAssetPrecision'],
                quote_precision=symbol['quotePrecision'],
                price=Price(
                    min=Decimal(price['minPrice']),
                    max=Decimal(price['maxPrice']),
                    step=Decimal(price['tickSize'])
                ),
                percent_price=PercentPrice(
                    multiplier_up=Decimal(percent_price['multiplierUp']),
                    multiplier_down=Decimal(percent_price['multiplierDown']),
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS
                ),
                size=Size(
                    min=Decimal(lot_size['minQty']),
                    max=Decimal(lot_size['maxQty']),
                    step=Decimal(lot_size['stepSize'])
                ),
                min_notional=MinNotional(
                    min_notional=Decimal(min_notional['minNotional']),
                    apply_to_market=min_notional['applyToMarket'],
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS
                )
            )
        return result

    @asynccontextmanager
    async def connect_stream_balances(self) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        async def inner() -> AsyncIterable[Dict[str, Balance]]:
            # Get initial status from REST API.
            res = await self._request('GET', '/api/v3/account', weight=5, security=_SEC_USER_DATA)
            result = {}
            for balance in res['balances']:
                result[
                    balance['asset'].lower()
                ] = Balance(available=Decimal(balance['free']), hold=Decimal(balance['locked']))
            yield result

            # Stream future updates over WS.
            # TODO: Note that someone else might consume the event data while we do the initial
            # fetch request. This might require a more sophisticated tracking impl.
            # For example, instead of pub/sub events, keep a queue of messages and deliver them
            # based on timestamps.
            while True:
                data = await self._balance_event.wait()
                result = {}
                for balance in data['B']:
                    result[
                        balance['a'].lower()
                    ] = Balance(available=Decimal(balance['f']), hold=Decimal(balance['l']))
                yield result

        await self._ensure_user_data_stream()
        yield inner()

    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[DepthUpdate]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[DepthUpdate]:
            # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#market-data-endpoints
            result = await self._request(
                'GET',
                '/api/v1/depth',
                weight=1,
                data={
                    'limit': 100,  # TODO: We might wanna increase that and accept higher weight.
                    'symbol': _http_symbol(symbol)
                }
            )
            yield DepthUpdate(
                type=DepthUpdateType.SNAPSHOT,
                bids=[(Decimal(x[0]), Decimal(x[1])) for x in result['bids']],
                asks=[(Decimal(x[0]), Decimal(x[1])) for x in result['asks']]
            )

            last_update_id = result['lastUpdateId']
            is_first_ws_message = True
            async for data in ws:
                if data['u'] <= last_update_id:
                    continue

                if is_first_ws_message:
                    assert data['U'] <= last_update_id + 1 and data['u'] >= last_update_id + 1
                    is_first_ws_message = False
                elif data['U'] != last_update_id + 1:
                    _log.warning(
                        f'orderbook out of sync: update id {data["U"]} != '
                        f'last update id {last_update_id} + 1; refetching snapshot'
                    )
                    async for data2 in inner(ws):
                        yield data2
                    break

                yield DepthUpdate(
                    type=DepthUpdateType.UPDATE,
                    bids=[(Decimal(m[0]), Decimal(m[1])) for m in data['b']],
                    asks=[(Decimal(m[0]), Decimal(m[1])) for m in data['a']]
                )
                last_update_id = data['u']

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#diff-depth-stream
        async with self._connect_refreshing_stream(
            url=f'/ws/{_ws_symbol(symbol)}@depth', interval=12 * HOUR_SEC, name='orderbook'
        ) as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_orders(self) -> AsyncIterator[AsyncIterable[OrderUpdate]]:
        async def inner() -> AsyncIterable[OrderUpdate]:
            while True:
                data = await self._order_event.wait()
                # fills = Fills()
                # fill_size = Decimal(data['l'])
                # if fill_size > 0:
                #     fills.append(Fill(
                #         price=Decimal(data['L']),
                #         size=fill_size,
                #         fee=Decimal(data['n']),
                #         fee_asset=data['N'].lower()))
                yield OrderUpdate(
                    symbol=_from_symbol(data['s']),
                    # 'status': data['x'],
                    status=_from_order_status(data['X']),
                    client_id=data['c'],
                    price=Decimal(data['p']),
                    size=Decimal(data['q']),
                    cumulative_filled_size=Decimal(data['z']),
                    # 'size': Decimal(data['q']),
                    # 'fills': fills,
                    fee=Decimal(data['n']),
                    fee_asset=data['N'].lower() if data['N'] else None
                )

        await self._ensure_user_data_stream()
        yield inner()

    async def _ensure_user_data_stream(self) -> None:
        async with self._listen_key_lock:
            if self._listen_key_refresh_task:
                return

            user_stream_connected = asyncio.Event()

            listen_key = (
                await self._request('POST', '/api/v1/userDataStream', security=_SEC_USER_STREAM)
            )['listenKey']
            self._listen_key_refresh_task = asyncio.create_task(
                cancelable(self._periodic_listen_key_refresh(listen_key))
            )
            self._stream_user_data_task = asyncio.create_task(
                cancelable(self._stream_user_data(listen_key, user_stream_connected))
            )

            await user_stream_connected.wait()

    async def _stream_user_data(self, listen_key: str, connected: asyncio.Event) -> None:
        bal_time, order_time = 0, 0
        # TODO: since binance may send out of sync, we need a better sln here for `take_until`.
        async with self._connect_refreshing_stream(
            url=f'/ws/{listen_key}', interval=12 * HOUR_SEC, name='user'
        ) as ws:
            connected.set()
            async for data in ws:
                # The data can come out of sync. Make sure to discard old updates.
                if data['e'] == 'outboundAccountInfo' and data['E'] >= bal_time:
                    bal_time = data['E']
                    self._balance_event.set(data)
                elif data['e'] == 'executionReport' and data['E'] >= order_time:
                    order_time = data['E']
                    self._order_event.set(data)

    async def place_order(
        self,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Decimal,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
        test: bool = True
    ) -> OrderResult:
        data = {
            'symbol': _http_symbol(symbol),
            'side': _side(side),
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
            ])
        )

    async def cancel_order(self, symbol: str, client_id: str) -> CancelOrderResult:
        data = {'symbol': _http_symbol(symbol), 'origClientOrderId': client_id}
        res = await self._request(
            'DELETE', '/api/v3/order', data=data, security=_SEC_TRADE, raise_for_status=False
        )
        binance_error = res.get('code')
        if binance_error == _ERR_CANCEL_REJECTED:
            return CancelOrderResult(status=CancelOrderStatus.REJECTED)
        if binance_error:
            raise NotImplementedError(f'No handling for binance error: {res}')
        return CancelOrderResult(status=CancelOrderStatus.SUCCESS)

    @asynccontextmanager
    async def connect_stream_candles(self, symbol: str, interval: int, start: int,
                                     end: int) -> AsyncIterator[AsyncIterable[Candle]]:
        current = floor_multiple(time_ms(), interval)
        future_stream = None

        async def inner() -> AsyncIterable[Candle]:
            if start < current:
                async for candle in self._stream_historical_candles(
                    symbol, interval, start, min(end, current)
                ):
                    yield candle
            if future_stream:
                async for candle in future_stream:
                    yield candle

        if end > current:
            async with self._stream_future_candles(symbol, interval, end) as future_stream:
                yield inner()
        else:
            yield inner()

    async def _stream_historical_candles(self, symbol: str, interval: int, start: int,
                                         end: int) -> AsyncIterable[Candle]:
        MAX_CANDLES_PER_REQUEST = 1000
        for page_start, page_end in page(start, end, interval, MAX_CANDLES_PER_REQUEST):
            res = await self._request(
                'GET',
                '/api/v1/klines',
                data={
                    'symbol': _http_symbol(symbol),
                    'interval': strfinterval(interval),
                    'startTime': page_start,
                    'endTime': page_end - 1,
                    'limit': MAX_CANDLES_PER_REQUEST
                }
            )
            for c in res:
                yield Candle(
                    c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
                    Decimal(c[5]), True
                )

    @asynccontextmanager
    async def _stream_future_candles(self, symbol: str, interval: int,
                                     end: int) -> AsyncIterator[AsyncIterable[Candle]]:
        # Binance disconnects a websocket connection every 24h. Therefore, we reconnect every 12h.
        # Note that two streams will send events with matching evt_times.
        # This can be used to switch from one stream to another and avoiding the edge case where
        # we miss out on the very last update to a candle.

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Candle]:
            async for data in ws:
                c = data['k']
                candle = Candle(
                    c['t'], Decimal(c['o']), Decimal(c['h']), Decimal(c['l']), Decimal(c['c']),
                    Decimal(c['v']), c['x']
                )
                yield candle

                if candle.time >= end - interval and candle.closed:
                    break

        async with self._connect_refreshing_stream(
            url=f'/ws/{_ws_symbol(symbol)}@kline_{strfinterval(interval)}',
            interval=12 * HOUR_SEC,
            name='candles'
        ) as ws:
            yield inner(ws)

    async def _periodic_listen_key_refresh(self, listen_key: str) -> None:
        try:
            while True:
                await asyncio.sleep(30 * MIN_SEC)
                await self._request(
                    'PUT',
                    '/api/v1/userDataStream',
                    data={'listenKey': listen_key},
                    security=_SEC_USER_STREAM
                )
        finally:
            await self._request(
                'DELETE',
                '/api/v1/userDataStream',
                data={'listenKey': listen_key},
                security=_SEC_USER_STREAM
            )

    async def _request(
        self,
        method: str,
        url: str,
        weight: int = 1,
        data: Optional[Any] = None,
        security: int = _SEC_NONE,
        raise_for_status: bool = True
    ) -> Any:
        if method == '/api/v3/order':
            await asyncio.gather(
                self._reqs_per_min_limiter.acquire(weight),
                self._orders_per_day_limiter.acquire(),
                self._orders_per_sec_limiter.acquire(),
            )
        else:
            await self._reqs_per_min_limiter.acquire(weight)

        kwargs: Dict[str, Any] = {}

        if security in [_SEC_TRADE, _SEC_USER_DATA, _SEC_USER_STREAM, _SEC_MARKET_DATA]:
            kwargs['headers'] = {'X-MBX-APIKEY': self._api_key}

        if security in [_SEC_TRADE, _SEC_USER_DATA]:
            # Synchronize clock. Note that we may want to do this periodically instead of only
            # initially.
            if not self._sync_clock_task:
                self._sync_clock_task = asyncio.create_task(cancelable(self._sync_clock()))
            await self._sync_clock_task

            data = data or {}
            data['timestamp'] = time_ms() + self._time_diff
            query_str_bytes = urllib.parse.urlencode(data).encode('utf-8')
            signature = hmac.new(self._secret_key_bytes, query_str_bytes, hashlib.sha256)
            data['signature'] = signature.hexdigest()

        if data:
            kwargs['params' if method == 'GET' else 'data'] = data

        async with self._session.request(method=method, url=_BASE_REST_URL + url, **kwargs) as res:
            if res.status in [418, 429]:
                retry_after = res.headers['Retry-After']
                _log.warning(f'received status {res.status}; retrying after {retry_after}s')
                await asyncio.sleep(float(retry_after))
            else:
                if raise_for_status:
                    res.raise_for_status()
                return await res.json(loads=lambda x: json.loads(x, use_decimal=True))

        return await self._request(method, url, weight, data, security, raise_for_status)

    def _connect_refreshing_stream(self, url: str, interval: int, name: str,
                                   **kwargs: Any) -> AsyncContextManager[AsyncIterable[Any]]:
        return connect_refreshing_stream(
            self._session,
            url=_BASE_WS_URL + url,
            interval=interval,
            loads=json.loads,
            take_until=lambda old, new: old['E'] < new['E'],
            name=name
        )

    async def _sync_clock(self) -> None:
        _log.info('syncing clock with Binance')
        before = time_ms()
        server_time = (await self._request('GET', '/api/v1/time'))['serverTime']
        after = time_ms()
        # Assume response time is same as request time.
        delay = (after - before) // 2
        local_time = before + delay
        # Adjustment required converting from local time to server time.
        self._time_diff = server_time - local_time
        _log.info(f'found {self._time_diff}ms time difference')
        # TODO: If we want to sync periodically, we should schedule a task on the event loop
        # to set self.sync_clock to None after a period of time. This will force re-sync.


def _http_symbol(symbol: str) -> str:
    return symbol.replace('-', '').upper()


def _ws_symbol(symbol: str) -> str:
    return symbol.replace('-', '')


def _from_symbol(symbol: str) -> str:
    # TODO: May be incorrect! We can't systematically know which part is base and which is quote
    # since there is no separator used. We simply map based on known base currencies.
    known_base_assets = [
        'BNB', 'BTC', 'ETH', 'XRP', 'USDT', 'PAX', 'TUSD', 'USDC', 'USDS', 'TRX', 'BUSD'
    ]
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


def _side(side: Side) -> str:
    return {
        Side.BUY: 'BUY',
        Side.SELL: 'SELL',
    }[side]


def _from_order_status(status: str) -> OrderStatus:
    status_map = {
        'NEW': OrderStatus.NEW,
        'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
        'FILLED': OrderStatus.FILLED,
        'CANCELED': OrderStatus.CANCELED
    }
    mapped_status = status_map.get(status)
    if not mapped_status:
        raise NotImplementedError(f'Handling of status {status} not implemented')
    return mapped_status
