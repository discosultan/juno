from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from time import time
from typing import Any, AsyncIterable, AsyncIterator, Dict, List, Optional, Union

from dateutil.tz import UTC

import juno.json as json
from juno import (
    Balance, CancelOrderResult, Candle, DepthSnapshot, DepthUpdate, Fees, Filters, OrderType, Side,
    SymbolsInfo, TimeInForce
)
from juno.asyncio import Event, cancel, cancelable
from juno.filters import Price, Size
from juno.http import ClientSession
from juno.math import floor_multiple
from juno.time import datetime_timestamp_ms, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import LeakyBucket, page

from .exchange import Exchange

_BASE_REST_URL = 'https://api.pro.coinbase.com'
_BASE_WS_URL = 'wss://ws-feed.pro.coinbase.com'

_log = logging.getLogger(__name__)


class Coinbase(Exchange):
    # Capabilities.
    can_stream_depth_snapshot: bool = True
    can_stream_candles: bool = False

    def __init__(self, api_key: str, secret_key: str, passphrase: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = base64.b64decode(secret_key)
        self._passphrase = passphrase

    async def __aenter__(self) -> Coinbase:
        # Rate limiter.
        self._pub_limiter = LeakyBucket(rate=1, period=1)  # They advertise 3 per sec.
        self._priv_limiter = LeakyBucket(rate=5, period=1)  # They advertise 5 per sec.

        # Stream.
        self._stream_task: Optional[asyncio.Task] = None
        self._stream_subscriptions: Dict[str, List[str]] = {}
        self._stream_subscription_queue: asyncio.Queue[Any] = asyncio.Queue()
        # TODO: Most probably require `autoclear=True`.
        self._stream_heartbeat_event: Event[Any] = Event()
        self._stream_depth_event: Event[Any] = Event()
        self._stream_match_event: Event[Any] = Event()
        self._stream_consumer_events = {
            'heartbeat': self._stream_heartbeat_event,
            'snapshot': self._stream_depth_event,
            'l2update': self._stream_depth_event,
            'match': self._stream_match_event
        }

        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._stream_task)
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_symbols_info(self) -> SymbolsInfo:
        # TODO: Fetch from exchange API if possible? Also has a more complex structure.
        # See https://support.pro.coinbase.com/customer/en/portal/articles/2945310-fees
        fees = {'__all__': Fees(maker=Decimal('0.0015'), taker=Decimal('0.0025'))}

        res = await self._public_request('GET', '/products')
        filters = {}
        for product in res:
            filters[product['id'].lower()] = Filters(
                price=Price(step=Decimal(product['quote_increment'])),
                size=Size(
                    min=Decimal(product['base_min_size']),
                    max=Decimal(product['base_max_size']),
                    step=Decimal(product['base_increment'])
                )
            )

        return SymbolsInfo(fees=fees, filters=filters)

    async def get_balances(self) -> Dict[str, Balance]:
        res = await self._private_request('GET', '/accounts')
        result = {}
        for balance in res:
            result[
                balance['currency'].lower()
            ] = Balance(available=Decimal(balance['available']), hold=Decimal(balance['hold']))
        return result

    @asynccontextmanager
    async def connect_stream_balances(self) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        async def inner() -> AsyncIterable[Dict[str, Balance]]:
            # TODO: Add support for future balance changes.
            yield {}

        yield inner()

    async def stream_historical_candles(self, symbol: str, interval: int, start: int,
                                        end: int) -> AsyncIterable[Candle]:
        MAX_CANDLES_PER_REQUEST = 300
        url = f'/products/{_product(symbol)}/candles'
        for page_start, page_end in page(start, end, interval, MAX_CANDLES_PER_REQUEST):
            res = await self._public_request(
                'GET', url, {
                    'start': _datetime(page_start),
                    'end': _datetime(page_end - 1),
                    'granularity': _granularity(interval)
                }
            )
            for c in reversed(res):
                # This seems to be an issue on Coinbase side. I didn't find any documentation for
                # this behavior but occasionally they send null values inside candle rows for
                # different price fields. Since we want to store all the data and we don't
                # currently use Coinbase for paper or live trading, we simply throw an exception.
                if None in c:
                    raise Exception(f'missing data for candle {c}; please re-run the command')
                yield Candle(
                    c[0] * 1000, Decimal(c[3]), Decimal(c[2]), Decimal(c[1]), Decimal(c[4]),
                    Decimal(c[5])
                )

    # TODO: First candle can be partial.
    @asynccontextmanager
    async def connect_stream_candles(self, symbol: str,
                                     interval: int) -> AsyncIterator[AsyncIterable[Candle]]:
        async def inner():
            self._ensure_stream_open()
            if symbol not in self._stream_subscriptions.get('matches', []):
                self._stream_subscription_queue.put_nowait({
                    'type': 'subscribe',
                    'product_ids': [_product(symbol)],
                    'channels': ['heartbeat', 'matches']
                })

            start = floor_multiple(time_ms(), interval)
            trades_since_start = []
            # TODO: pagination
            latest_trades = await self._public_request(
                'GET', f'/products/{_product(symbol)}/trades'
            )
            for trade in latest_trades:
                trade['time'] = _from_datetime(trade['time'])
                if trade['time'] < start:
                    break
                trades_since_start.append(trade)

            candles: Dict[str, Dict[int, Candle]] = defaultdict(dict)
            last_candle_map: Dict[str, Candle] = {}
            while True:
                data = await self._stream_match_event.wait()
                if 'price' not in data or 'size' not in data:
                    continue
                product_id = data['product_id']
                price, size = Decimal(data['price']), Decimal(data['size'])
                time = floor_multiple(_from_datetime(data['time']), interval)
                current_candle = candles[product_id].get(time)
                if not current_candle:
                    last_candle = last_candle_map.get(product_id)
                    if last_candle:
                        del candles[product_id][last_candle.time]
                        yield last_candle
                    candles[product_id][time] = Candle(
                        time=time,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=size,
                    )
                else:
                    current_candle = Candle(
                        time=current_candle.time,
                        open=current_candle.open,
                        high=max(price, current_candle.high),
                        low=min(price, current_candle.low),
                        close=price,
                        volume=current_candle.volume + size,
                    )
                    last_candle_map[product_id] = current_candle

        yield inner()

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Union[DepthSnapshot, DepthUpdate]]]:
        # TODO: await till stream open
        self._ensure_stream_open()
        if symbol not in self._stream_subscriptions.get('level2', []):
            self._stream_subscription_queue.put_nowait({
                'type': 'subscribe',
                'product_ids': [_product(symbol)],
                'channels': ['level2']
            })

        async def inner():
            while True:
                data = await self._stream_depth_event.wait()
                if data['type'] == 'snapshot':
                    yield DepthSnapshot(
                        bids=[(Decimal(p), Decimal(s)) for p, s in data['bids']],
                        asks=[(Decimal(p), Decimal(s)) for p, s in data['asks']]
                    )
                elif data['type'] == 'l2update':
                    bids = ((p, s) for side, p, s in data['changes'] if side == 'buy')
                    asks = ((p, s) for side, p, s in data['changes'] if side == 'sell')
                    yield DepthUpdate(
                        bids=[(Decimal(p), Decimal(s)) for p, s in bids],
                        asks=[(Decimal(p), Decimal(s)) for p, s in asks]
                    )

        yield inner()

    @asynccontextmanager
    async def connect_stream_orders(self) -> AsyncIterator[AsyncIterable[Any]]:
        raise NotImplementedError()
        yield

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
    ) -> Any:
        raise NotImplementedError()

    async def cancel_order(self, symbol: str, client_id: str) -> CancelOrderResult:
        raise NotImplementedError()

    def _ensure_stream_open(self) -> None:
        if not self._stream_task:
            self._stream_task = asyncio.create_task(cancelable(self._stream()))

    async def _stream(self) -> None:
        async with self._session.ws_connect(_BASE_WS_URL) as ws:
            for _ in range(0, self._stream_subscription_queue.qsize()):
                await ws.send_json(self._stream_subscription_queue.get_nowait())
            async for msg in ws:
                data = json.loads(msg.data)
                if data['type'] == 'subscriptions':
                    self._stream_subscriptions = {
                        c['name']: [s.lower() for s in c['product_ids']]
                        for c in data['channels']
                    }
                else:
                    self._stream_consumer_events[data['type']].set(data)

    async def _paginated_public_request(self, method: str, url: str,
                                        data: Dict[str, Any] = {}) -> AsyncIterable[Any]:
        url = _BASE_REST_URL + url
        page_after = None
        while True:
            await self._pub_limiter.acquire()
            if page_after is not None:
                data['after'] = page_after
            async with self._session.request(method, url, params=data) as res:
                yield await res.json(loads=json.loads)
                page_after = res.headers.get('CB-AFTER')
                if page_after is None:
                    break

    async def _public_request(self, method: str, url: str, data: Dict[str, Any] = {}) -> Any:
        async for val in self._paginated_public_request(method, url, data):
            return val  # Return only first.

    async def _private_request(self, method: str, url: str, data: str = '') -> Any:
        await self._priv_limiter.acquire()
        timestamp = str(time())
        message = (timestamp + method + url + data).encode('ascii')
        signature_hash = hmac.new(self._secret_key_bytes, message, hashlib.sha256).digest()
        signature = base64.b64encode(signature_hash).decode('ascii')
        headers = {
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-KEY': self._api_key,
            'CB-ACCESS-PASSPHRASE': self._passphrase
        }
        url = _BASE_REST_URL + url
        async with self._session.request(method, url, headers=headers, data=data) as res:
            return await res.json(loads=json.loads)


def _product(symbol: str) -> str:
    return symbol.upper()


def _granularity(interval: int) -> int:
    return interval // 1000


def _datetime(timestamp: int) -> str:
    return datetime.utcfromtimestamp(timestamp / 1000.0).isoformat()


def _from_datetime(dt: str) -> int:
    return datetime_timestamp_ms(
        datetime.strptime(dt, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=UTC)
    )
