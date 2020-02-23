from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import urllib.parse
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator, Dict, List, Optional, Union

import aiohttp
from tenacity import (
    before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential
)

from juno import (
    Balance, CancelOrderResult, CancelOrderStatus, Candle, DepthSnapshot, DepthUpdate,
    ExchangeInfo, Fees, Fill, JunoException, OrderResult, OrderStatus, OrderType, OrderUpdate,
    Side, Ticker, TimeInForce, Trade, json
)
from juno.asyncio import Event, cancel, cancelable
from juno.filters import Filters, MinNotional, PercentPrice, Price, Size
from juno.http import ClientJsonResponse, ClientSession, connect_refreshing_stream
from juno.itertools import page
from juno.time import DAY_SEC, HOUR_MS, HOUR_SEC, MIN_MS, MIN_SEC, strfinterval, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import AsyncLimiter

from .exchange import Exchange

_BASE_REST_URL = 'https://api.binance.com'
_BASE_WS_URL = 'wss://stream.binance.com:9443'

_SEC_NONE = 0  # Endpoint can be accessed freely.
_SEC_TRADE = 1  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_DATA = 2  # Endpoint requires sending a valid API-Key and signature.
_SEC_USER_STREAM = 3  # Endpoint requires sending a valid API-Key.
_SEC_MARKET_DATA = 4  # Endpoint requires sending a valid API-Key.

_ERR_CANCEL_REJECTED = -2011
_ERR_INVALID_TIMESTAMP = -1021
_ERR_LISTEN_KEY_DOES_NOT_EXIST = -1125

_log = logging.getLogger(__name__)


class Binance(Exchange):
    # Capabilities.
    can_stream_balances: bool = True
    can_stream_depth_snapshot: bool = False
    can_stream_historical_candles: bool = True
    can_stream_historical_earliest_candle: bool = True
    can_stream_candles: bool = True
    can_list_all_tickers: bool = True

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')

        self._session = ClientSession(raise_for_status=False)

        # Rate limiters.
        x = 0.5  # We use this factor to be on the safe side and not use up the entire bucket.
        self._reqs_per_min_limiter = AsyncLimiter(1200 * x, 60)
        self._raw_reqs_limiter = AsyncLimiter(5000 * x, 300)
        self._orders_per_sec_limiter = AsyncLimiter(10 * x, 1)
        self._orders_per_day_limiter = AsyncLimiter(100_000 * x, DAY_SEC)

        self._clock = Clock(self)
        self._user_data_stream = UserDataStream(self)

    async def __aenter__(self) -> Binance:
        await self._session.__aenter__()
        await asyncio.gather(
            self._clock.__aenter__(),
            self._user_data_stream.__aenter__(),
        )
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(
            self._user_data_stream.__aexit__(exc_type, exc, tb),
            self._clock.__aexit__(exc_type, exc, tb),
        )
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_exchange_info(self) -> ExchangeInfo:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/wapi-api.md#trade-fee-user_data
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#exchange-information
        fees_res, filters_res = await asyncio.gather(
            self._wapi_request('GET', '/wapi/v3/tradeFee.html', security=_SEC_USER_DATA),
            self._api_request('GET', '/api/v3/exchangeInfo'),
        )
        fees = {
            _from_symbol(fee['symbol']):
            Fees(maker=Decimal(fee['maker']), taker=Decimal(fee['taker']))
            for fee in fees_res.data['tradeFee']
        }
        filters = {}
        for symbol in filters_res.data['symbols']:
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

            filters[f"{symbol['baseAsset'].lower()}-{symbol['quoteAsset'].lower()}"] = Filters(
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
        return ExchangeInfo(
            fees=fees,
            filters=filters,
            candle_intervals=[
                60000, 180000, 300000, 900000, 1800000, 3600000, 7200000, 14400000, 21600000,
                28800000, 43200000, 86400000, 259200000, 604800000, 2629746000
            ]
        )

    async def list_tickers(self, symbols: List[str] = []) -> List[Ticker]:
        if len(symbols) > 1:
            raise NotImplementedError()

        data = {'symbol': _http_symbol(symbols[0])} if symbols else None
        weight = 1 if symbols else 40
        res = await self._api_request('GET', '/api/v3/ticker/24hr', data=data, weight=weight)
        response_data = [res.data] if symbols else res.data
        return [
            Ticker(
                symbol=_from_symbol(t['symbol']),
                volume=Decimal(t['volume']),
                quote_volume=Decimal(t['quoteVolume'])
            ) for t in response_data
        ]

    async def get_balances(self) -> Dict[str, Balance]:
        res = await self._api_request('GET', '/api/v3/account', weight=5, security=_SEC_USER_DATA)
        return {
            b['asset'].lower(): Balance(available=Decimal(b['free']), hold=Decimal(b['locked']))
            for b in res.data['balances']
        }

    @asynccontextmanager
    async def connect_stream_balances(self) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        async def inner(
            stream: AsyncIterable[Dict[str, Any]]
        ) -> AsyncIterable[Dict[str, Balance]]:
            async for data in stream:
                result = {}
                for balance in data['B']:
                    result[
                        balance['a'].lower()
                    ] = Balance(available=Decimal(balance['f']), hold=Decimal(balance['l']))
                yield result

        async with self._user_data_stream.subscribe('outboundAccountInfo') as stream:
            yield inner(stream)

    async def get_depth(self, symbol: str) -> DepthSnapshot:
        # TODO: We might wanna increase that and accept higher weight.
        LIMIT = 100
        LIMIT_TO_WEIGHT = {
            5: 1,
            10: 1,
            20: 1,
            50: 1,
            100: 1,
            500: 5,
            1000: 10,
            5000: 50,
        }
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#market-data-endpoints
        res = await self._api_request(
            'GET',
            '/api/v3/depth',
            weight=LIMIT_TO_WEIGHT[LIMIT],
            data={
                'limit': LIMIT,
                'symbol': _http_symbol(symbol)
            }
        )
        return DepthSnapshot(
            bids=[(Decimal(x[0]), Decimal(x[1])) for x in res.data['bids']],
            asks=[(Decimal(x[0]), Decimal(x[1])) for x in res.data['asks']],
            last_id=res.data['lastUpdateId'],
        )

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Union[DepthSnapshot, DepthUpdate]]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[DepthUpdate]:
            async for data in ws:
                yield DepthUpdate(
                    bids=[(Decimal(m[0]), Decimal(m[1])) for m in data['b']],
                    asks=[(Decimal(m[0]), Decimal(m[1])) for m in data['a']],
                    first_id=data['U'],
                    last_id=data['u']
                )

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#diff-depth-stream
        async with self._connect_refreshing_stream(
            url=f'/ws/{_ws_symbol(symbol)}@depth@100ms', interval=12 * HOUR_SEC, name='depth',
            raise_on_disconnect=True
        ) as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_orders(self) -> AsyncIterator[AsyncIterable[OrderUpdate]]:
        async def inner(stream: AsyncIterable[Dict[str, Any]]) -> AsyncIterable[OrderUpdate]:
            async for data in stream:
                yield OrderUpdate(
                    symbol=_from_symbol(data['s']),
                    status=_from_order_status(data['X']),
                    # 'c' is client order id, 'C' is original client order id. 'C' is usually empty
                    # except for when an order gets cancelled; in that case 'c' has a new value.
                    client_id=data['C'] if data['C'] else data['c'],
                    price=Decimal(data['p']),
                    size=Decimal(data['q']),
                    filled_size=Decimal(data['l']),
                    cumulative_filled_size=Decimal(data['z']),
                    fee=Decimal(data['n']),
                    fee_asset=data['N'].lower() if data['N'] else None
                )

        async with self._user_data_stream.subscribe('executionReport') as stream:
            yield inner(stream)

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
        res = await self._api_request('POST', url, data=data, security=_SEC_TRADE)
        if test:
            return OrderResult.not_placed()
        return OrderResult(
            status=_from_order_status(res.data['status']),
            fills=[
                Fill(
                    price=Decimal(f['price']),
                    size=Decimal(f['qty']),
                    fee=Decimal(f['commission']),
                    fee_asset=f['commissionAsset'].lower()
                ) for f in res.data['fills']
            ]
        )

    async def cancel_order(self, symbol: str, client_id: str) -> CancelOrderResult:
        data = {'symbol': _http_symbol(symbol), 'origClientOrderId': client_id}
        res = await self._api_request(
            'DELETE', '/api/v3/order', data=data, security=_SEC_TRADE, raise_for_status=False
        )
        binance_error = res.data.get('code')
        if binance_error == _ERR_CANCEL_REJECTED:
            return CancelOrderResult(status=CancelOrderStatus.REJECTED)
        if binance_error:
            raise NotImplementedError(f'No handling for binance error: {res}')
        return CancelOrderResult(status=CancelOrderStatus.SUCCESS)

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        limit = 1000  # Max possible candles per request.
        # Start 0 is a special value indicating that we try to find the earliest available candle.
        pagination_interval = interval
        if start == 0:
            pagination_interval = end - start
        for page_start, page_end in page(start, end, pagination_interval, limit):
            res = await self._api_request(
                'GET',
                '/api/v3/klines',
                data={
                    'symbol': _http_symbol(symbol),
                    'interval': strfinterval(interval),
                    'startTime': page_start,
                    'endTime': page_end - 1,
                    'limit': limit
                }
            )
            for c in res.data:
                yield Candle(
                    c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
                    Decimal(c[5]), True
                )

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        # Binance disconnects a websocket connection every 24h. Therefore, we reconnect every 12h.
        # Note that two streams will send events with matching evt_times.
        # This can be used to switch from one stream to another and avoiding the edge case where
        # we miss out on the very last update to a candle.

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Candle]:
            async for data in ws:
                c = data['k']
                yield Candle(
                    c['t'], Decimal(c['o']), Decimal(c['h']), Decimal(c['l']), Decimal(c['c']),
                    Decimal(c['v']), c['x']
                )

        async with self._connect_refreshing_stream(
            url=f'/ws/{_ws_symbol(symbol)}@kline_{strfinterval(interval)}',
            interval=12 * HOUR_SEC,
            name='candles',
            raise_on_disconnect=True
        ) as ws:
            yield inner(ws)

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        # Aggregated trades. This means trades executed at the same time, same price and as part of
        # the same order will be aggregated by summing their size.
        batch_start = start
        payload: Dict[str, Any] = {
            'symbol': _http_symbol(symbol),
        }
        while True:
            batch_end = batch_start + HOUR_MS
            payload['startTime'] = batch_start
            payload['endTime'] = min(batch_end, end) - 1  # Inclusive.

            time = None

            res = await self._api_request('GET', '/api/v3/aggTrades', data=payload)
            for t in res.data:
                time = t['T']
                assert time < end
                yield Trade(
                    id=t['a'],
                    time=time,
                    price=Decimal(t['p']),
                    size=Decimal(t['q']),
                )
            batch_start = time + 1 if time is not None else batch_end
            if batch_start >= end:
                break

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Trade]:
            async for data in ws:
                yield Trade(
                    id=data['a'],
                    time=data['T'],
                    price=Decimal(data['p']),
                    size=Decimal(data['q']),
                )

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#trade-streams
        async with self._connect_refreshing_stream(
            url=f'/ws/{_ws_symbol(symbol)}@trade', interval=12 * HOUR_SEC, name='trade',
            raise_on_disconnect=True
        ) as ws:
            yield inner(ws)

    async def _wapi_request(
        self,
        method: str,
        url: str,
        weight: int = 1,
        data: Optional[Any] = None,
        security: int = _SEC_NONE,
        raise_for_status=True
    ) -> Any:
        res = await self._request(
            method=method,
            url=url,
            weight=weight,
            data=data,
            security=security,
            raise_for_status=raise_for_status,
        )
        if not res.data['success']:
            # There's no error code in this response to figure out whether it's a timestamp issue.
            # We could look it up from the message, but currently just assume that is the case
            # always.
            _log.warning(f'received error: {res.data["msg"]}; syncing clock before exc')
            self._clock.clear()
            raise JunoException(res.data['msg'])
        return res

    async def _api_request(
        self,
        method: str,
        url: str,
        weight: int = 1,
        data: Optional[Any] = None,
        security: int = _SEC_NONE,
        raise_for_status=True,
    ) -> Any:
        res = await self._request(
            method=method,
            url=url,
            weight=weight,
            data=data,
            security=security,
            raise_for_status=raise_for_status,
        )
        if isinstance(res.data, dict) and res.data.get('code') == _ERR_INVALID_TIMESTAMP:
            _log.warning(f'received invalid timestamp; syncing clock before exc')
            self._clock.clear()
            raise JunoException('Incorrect timestamp')
        return res

    async def _request(
        self,
        method: str,
        url: str,
        weight: int = 1,
        data: Optional[Any] = None,
        security: int = _SEC_NONE,
        raise_for_status: bool = True
    ) -> ClientJsonResponse:
        limiters = [
            self._raw_reqs_limiter.acquire(),
            self._reqs_per_min_limiter.acquire(weight),
        ]
        if method == '/api/v3/order':
            limiters.extend((
                self._orders_per_day_limiter.acquire(),
                self._orders_per_sec_limiter.acquire(),
            ))
        await asyncio.gather(*limiters)

        kwargs: Dict[str, Any] = {}

        if security in [_SEC_TRADE, _SEC_USER_DATA, _SEC_USER_STREAM, _SEC_MARKET_DATA]:
            kwargs['headers'] = {'X-MBX-APIKEY': self._api_key}

        if security in [_SEC_TRADE, _SEC_USER_DATA]:
            await self._clock.wait()

            data = data or {}
            data['timestamp'] = time_ms() + self._clock.time_diff
            query_str_bytes = urllib.parse.urlencode(data).encode('utf-8')
            signature = hmac.new(self._secret_key_bytes, query_str_bytes, hashlib.sha256)
            data['signature'] = signature.hexdigest()

        if data:
            kwargs['params' if method == 'GET' else 'data'] = data

        async with self._session.request_json(
            method=method, url=_BASE_REST_URL + url, **kwargs
        ) as res:
            if res.status in [418, 429]:
                retry_after = res.headers['Retry-After']
                _log.warning(f'received status {res.status}; sleeping {retry_after}s before exc')
                await asyncio.sleep(float(retry_after))
                raise JunoException('Retry after')
            else:
                if raise_for_status:
                    res.raise_for_status()
                return res

    @asynccontextmanager
    async def _connect_refreshing_stream(
        self, url: str, interval: int, name: str, raise_on_disconnect: bool = False
    ) -> AsyncIterator[AsyncIterable[Any]]:
        try:
            async with connect_refreshing_stream(
                self._session,
                url=_BASE_WS_URL + url,
                interval=interval,
                loads=json.loads,
                take_until=lambda old, new: old['E'] < new['E'],
                name=name,
                raise_on_disconnect=raise_on_disconnect
            ) as stream:
                yield stream
        except aiohttp.WebSocketError as e:
            raise JunoException(str(e))


class Clock:
    def __init__(self, binance: Binance) -> None:
        self.time_diff = 0
        self._binance = binance
        self._synced = asyncio.Event()
        self._periodic_sync_task: Optional[asyncio.Task[None]] = None
        self._reset_periodic_sync: Event[None] = Event(autoclear=True)

    async def __aenter__(self) -> Clock:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._periodic_sync_task)

    async def wait(self) -> None:
        if not self._periodic_sync_task:
            self._periodic_sync_task = asyncio.create_task(cancelable(self._periodic_sync()))

        await self._synced.wait()

    def clear(self) -> None:
        self._synced.clear()
        if self._periodic_sync_task:
            self._reset_periodic_sync.set()

    async def _periodic_sync(self) -> None:
        while True:
            await self._sync_clock()
            sleep_task = asyncio.create_task(asyncio.sleep(HOUR_SEC * 12))
            try:
                await asyncio.wait(
                    [sleep_task, self._reset_periodic_sync.wait()],
                    return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                if not sleep_task.done():
                    with suppress(asyncio.CancelledError):
                        await cancel(sleep_task)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.DEBUG)
    )
    async def _sync_clock(self) -> None:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#check-server-time
        _log.info('syncing clock with Binance')
        before = time_ms()
        server_time = (await self._binance._api_request('GET', '/api/v3/time')).data['serverTime']
        after = time_ms()
        # Assume response time is same as request time.
        delay = (after - before) // 2
        local_time = before + delay
        # Adjustment required converting from local time to server time.
        self.time_diff = server_time - local_time
        _log.info(f'found {self.time_diff}ms time difference')
        self._synced.set()


class UserDataStream:
    def __init__(self, binance: Binance) -> None:
        self._binance = binance
        self._listen_key_lock = asyncio.Lock()
        self._stream_connected = asyncio.Event()
        self._listen_key = None

        self._listen_key_refresh_task: Optional[asyncio.Task[None]] = None
        self._stream_user_data_task: Optional[asyncio.Task[None]] = None
        self._old_tasks: List[asyncio.Task[None]] = []

        self._events: Dict[str, Event[Any]] = defaultdict(lambda: Event(autoclear=True))

    async def __aenter__(self) -> UserDataStream:
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        # We could delete a listen key here but we don't. Listen key is scoped to account and we
        # don't want to delete listen keys for other juno instances tied to the same account.
        # It will get deleted automatically by Binance after 60 mins of inactivity.
        # if self._listen_key:
        #     await self._delete_listen_key(self._listen_key)
        await cancel(self._listen_key_refresh_task, self._stream_user_data_task)

    @asynccontextmanager
    async def subscribe(self, event_type: str) -> AsyncIterator[AsyncIterable[Any]]:
        # TODO: Note that someone else might consume the event data while we do the initial
        # fetch request. This might require a more sophisticated tracking impl.
        # For example, instead of pub/sub events, keep a queue of messages and deliver them
        # based on timestamps.
        await self._ensure_connection()

        event = self._events[event_type]

        async def inner(event: Event[Any]) -> AsyncIterable[Any]:
            while True:
                data = await event.wait()
                if isinstance(data, Exception):
                    raise data
                yield data

        try:
            yield inner(event)
        finally:
            # TODO: unsubscribe if no other consumers?
            pass

    async def _ensure_listen_key(self) -> None:
        async with self._listen_key_lock:
            if not self._listen_key:
                self._listen_key = (await self._create_listen_key()).data['listenKey']

    async def _ensure_connection(self) -> None:
        await self._ensure_listen_key()

        if not self._listen_key_refresh_task:
            self._listen_key_refresh_task = asyncio.create_task(
                cancelable(self._periodic_listen_key_refresh())
            )

        if not self._stream_user_data_task:
            self._stream_user_data_task = asyncio.create_task(
                cancelable(self._stream_user_data())
            )

        await self._stream_connected.wait()

    async def _periodic_listen_key_refresh(self) -> None:
        while True:
            await asyncio.sleep(30 * MIN_SEC)
            if self._listen_key:
                try:
                    await self._update_listen_key(self._listen_key)
                except JunoException:
                    _log.warning(f'tried to update a listen key {self._listen_key} which did not '
                                 'exist; resetting')
                    self._listen_key = None
                    await self._ensure_listen_key()
            else:
                _log.warning('want to refresh listen key but missing locally')

    async def _stream_user_data(self) -> None:
        while True:
            try:
                async with self._binance._connect_refreshing_stream(
                    url=f'/ws/{self._listen_key}', interval=12 * HOUR_SEC, name='user',
                    raise_on_disconnect=True
                ) as stream:
                    self._stream_connected.set()
                    async for data in stream:
                        self._events[data['e']].set(data)
                break
            except JunoException as e:
                for event in self._events.values():
                    event.set(e)
            await self._ensure_listen_key()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.DEBUG)
    )
    async def _create_listen_key(self) -> ClientJsonResponse:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#create-a-listenkey
        return await self._binance._api_request(
            'POST',
            '/api/v3/userDataStream',
            security=_SEC_USER_STREAM
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.DEBUG)
    )
    async def _update_listen_key(self, listen_key: str) -> ClientJsonResponse:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#pingkeep-alive-a-listenkey
        res = await self._binance._api_request(
            'PUT',
            '/api/v3/userDataStream',
            data={'listenKey': listen_key},
            security=_SEC_USER_STREAM,
            raise_for_status=False
        )
        if res.status == 400 and res.data.get('code') == _ERR_LISTEN_KEY_DOES_NOT_EXIST:
            raise JunoException('Listen key does not exist')
        res.raise_for_status()
        return res

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(),
        retry=retry_if_exception_type(
            (aiohttp.ClientConnectionError, aiohttp.ClientResponseError)
        ),
        before_sleep=before_sleep_log(_log, logging.DEBUG)
    )
    async def _delete_listen_key(self, listen_key: str) -> ClientJsonResponse:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#close-a-listenkey
        return await self._binance._api_request(
            'DELETE',
            '/api/v3/userDataStream',
            data={'listenKey': listen_key},
            security=_SEC_USER_STREAM
        )


def _http_symbol(symbol: str) -> str:
    return symbol.replace('-', '').upper()


def _ws_symbol(symbol: str) -> str:
    return symbol.replace('-', '')


def _from_symbol(symbol: str) -> str:
    # TODO: May be incorrect! We can't systematically know which part is base and which is quote
    # since there is no separator used. We simply map based on known base currencies.
    known_base_assets = [
        'BNB', 'BTC', 'ETH', 'XRP', 'USDT', 'PAX', 'TUSD', 'USDC', 'USDS', 'TRX', 'BUSD', 'NGN',
        'RUB', 'TRY', 'EUR'
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
