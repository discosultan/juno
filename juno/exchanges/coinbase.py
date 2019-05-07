from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from time import time
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple

import simplejson as json

from juno import Balance, Candle, Fees, OrderType, Side, SymbolInfo, TimeInForce
from juno.http import ClientSession
from juno.math import floor_multiple
from juno.time import datetime_timestamp_ms, time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import Event, LeakyBucket, page

from .exchange import Exchange

_BASE_REST_URL = 'https://api.pro.coinbase.com'
_BASE_WS_URL = 'wss://ws-feed.pro.coinbase.com'

_log = logging.getLogger(__name__)


class Coinbase(Exchange):

    def __init__(self, api_key: str, secret_key: str, passphrase: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = base64.b64decode(secret_key)
        self._passphrase = passphrase

    async def __aenter__(self) -> Coinbase:
        # Rate limiter.
        self._pub_limiter = LeakyBucket(rate=1, period=1)   # They advertise 3 per sec.
        self._priv_limiter = LeakyBucket(rate=5, period=1)  # They advertise 5 per sec.

        # Stream.
        self._stream_task = None
        self._stream_subscriptions: Dict[str, List[str]] = {}
        self._stream_subscription_queue: asyncio.Queue[Any] = asyncio.Queue()
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
        if self._stream_task:
            self._stream_task.cancel()
            await self._stream_task
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_fees(self) -> Dict[str, Fees]:
        # TODO: Fetch from exchange API if possible? Also has a more complex structure.
        # See https://support.pro.coinbase.com/customer/en/portal/articles/2945310-fees
        return {'__all__': Fees(maker=Decimal('0.0015'), taker=Decimal('0.0025'))}

    async def map_symbol_infos(self) -> Dict[str, SymbolInfo]:
        res = await self._public_request('GET', '/products')
        result = {}
        for product in res:
            result[product['id'].lower()] = SymbolInfo(
                min_size=Decimal(product['base_min_size']),
                max_size=Decimal(product['base_max_size']),
                size_step=Decimal(product['base_min_size']),
                min_price=Decimal(product['min_market_funds']),
                max_price=Decimal(product['max_market_funds']),
                price_step=Decimal(product['quote_increment']))
        return result

    async def stream_balances(self) -> AsyncIterable[Dict[str, Balance]]:
        res = await self._private_request('GET', '/accounts')
        result = {}
        for balance in res:
            result[balance['currency'].lower()] = Balance(
                available=Decimal(balance['available']),
                hold=Decimal(balance['hold']))
        yield result

        # TODO: Add support for future balance changes.

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

    async def _stream_historical_candles(self, symbol, interval, start, end):
        MAX_CANDLES_PER_REQUEST = 300  # They advertise 350.
        url = f'/products/{_product(symbol)}/candles'
        for page_start, page_end in page(start, end, interval, MAX_CANDLES_PER_REQUEST):
            res = await self._public_request('GET', url, {
                'start': _datetime(page_start),
                'end': _datetime(page_end),
                'granularity': _granularity(interval)
            })
            for c in reversed(res):
                # This seems to be an issue on Coinbase side. I didn't find any documentation for
                # this behavior but occasionally they send null values inside candle rows for
                # different price fields. Since we want to store all the data and we don't
                # currently use Coinbase for paper or live trading, we simply throw an exception.
                if None in c:
                    raise Exception(f'missing data for candle {c}; please re-run the command')
                yield Candle(c[0] * 1000, c[3], c[2], c[1], c[4], c[5]), True

    # TODO: First candle can be partial.
    async def _stream_future_candles(self, symbol, interval, end):
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
        latest_trades = await self._public_request('GET', f'/products/{_product(symbol)}/trades')
        for trade in latest_trades:
            trade['time'] = _from_datetime(trade['time'])
            if trade['time'] < start:
                break
            trades_since_start.append(trade)

        candles = defaultdict(dict)
        last_candle_map = {}
        while True:
            data = await self._stream_match_event.wait()
            if 'price' not in data or 'size' not in data:
                continue
            product_id = data['product_id']
            price, size = Decimal(data['price']), Decimal(data['size'])
            time = floor_multiple(_from_datetime(data['time']), interval)
            current_candle = candles[product_id].get(time)
            if not current_candle:
                last_candle = last_candle_map.get[product_id]
                if last_candle:
                    del candles[product_id][last_candle.time]
                    yield last_candle, True
                candles[product_id][time] = Candle(
                    time=time,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=size
                )
            else:
                current_candle.high = max(price, current_candle.high)
                current_candle.low = min(price, current_candle.low)
                current_candle.close = price
                current_candle.volume = current_candle.volume + size
                last_candle_map[product_id] = current_candle

    async def stream_depth(self, symbol):
        self._ensure_stream_open()
        if symbol not in self._stream_subscriptions.get('level2', []):
            self._stream_subscription_queue.put_nowait({
                'type': 'subscribe',
                'product_ids': [_product(symbol)],
                'channels': ['level2']
            })
        while True:
            data = await self._stream_depth_event.wait()
            if data['type'] == 'snapshot':
                yield {
                    'type': 'snapshot',
                    'bids': [(Decimal(p), Decimal(s)) for p, s in data['bids']],
                    'asks': [(Decimal(p), Decimal(s)) for p, s in data['asks']]
                }
            elif data['type'] == 'l2update':
                bids = ((p, s) for side, p, s in data['changes'] if side == 'buy')
                asks = ((p, s) for side, p, s in data['changes'] if side == 'sell')
                yield {
                    'type': 'update',
                    'bids': [(Decimal(p), Decimal(s)) for p, s in bids],
                    'asks': [(Decimal(p), Decimal(s)) for p, s in asks]
                }

    async def stream_orders(self) -> AsyncIterable[Any]:
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
            test: bool = True) -> Any:
        raise NotImplementedError()

    async def cancel_order(self, symbol: str, client_id: str) -> Any:
        raise NotImplementedError()

    def _ensure_stream_open(self):
        if not self._stream_task:
            self._stream_task = asyncio.create_task(self._stream())

    async def _stream(self):
        try:
            async with self._session.ws_connect(_BASE_WS_URL) as ws:
                for _ in range(0, self._stream_subscription_queue.qsize()):
                    await ws.send_json(self._stream_subscription_queue.get_nowait())
                async for msg in ws:
                    data = json.loads(msg.data)
                    if data['type'] == 'subscriptions':
                        self._stream_subscriptions = {
                            c['name']: [s.lower() for s in c['product_ids']]
                            for c in data['channels']}
                    else:
                        self._stream_consumer_events[data['type']].set(data)
        except asyncio.CancelledError:
            _log.info('streaming task cancelled')

    async def _paginated_public_request(self, method, url, data={}):
        url = _BASE_REST_URL + url
        page_after = None
        while True:
            # TODO: retry with backoff
            await self._pub_limiter.acquire()
            if page_after is not None:
                data['after'] = page_after
            async with self._session.request(method, url, params=data) as res:
                yield await res.json(loads=lambda x: json.loads(x, use_decimal=True))
                page_after = res.headers.get('CB-AFTER')
                if page_after is None:
                    break

    async def _public_request(self, method, url, data={}):
        # TODO: raises RuntimeError due to https://bugs.python.org/issue33786
        stream = self._paginated_public_request(method, url, data)
        val = await stream.__anext__()
        return val

    # TODO: retry with backoff
    async def _private_request(self, method, url, body=''):
        await self._priv_limiter.acquire()
        timestamp = str(time())
        message = (timestamp + method + url + body).encode('ascii')
        signature_hash = hmac.new(self._secret_key_bytes, message, hashlib.sha256).digest()
        signature = base64.b64encode(signature_hash).decode('ascii')
        headers = {
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-KEY': self._api_key,
            'CB-ACCESS-PASSPHRASE': self._passphrase}
        url = _BASE_REST_URL + url
        async with self._session.request(method, url, headers=headers, data=body) as res:
            return await res.json(loads=lambda x: json.loads(x, use_decimal=True))


def _product(symbol: str) -> str:
    return symbol.upper()


def _granularity(interval: int) -> int:
    return interval // 1000


def _datetime(timestamp: int) -> str:
    return datetime.utcfromtimestamp(timestamp / 1000.0).isoformat()


def _from_datetime(dt: str) -> int:
    return datetime_timestamp_ms(datetime.strptime(dt, '%Y-%m-%dT%H:%M:%S.%fZ'))
