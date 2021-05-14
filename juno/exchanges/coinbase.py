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
from typing import Any, AsyncContextManager, AsyncIterable, AsyncIterator, Optional

from dateutil.tz import UTC

from juno import (
    AssetInfo,
    BadOrder,
    Balance,
    Candle,
    Depth,
    ExchangeException,
    ExchangeInfo,
    Fees,
    Fill,
    Filters,
    OrderMissing,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderUpdate,
    Side,
    Ticker,
    TimeInForce,
    Trade,
    json,
)
from juno.asyncio import Event, cancel, create_task_sigint_on_exception, merge_async, stream_queue
from juno.http import ClientResponse, ClientSession, ClientWebSocketResponse
from juno.time import datetime_timestamp_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import AsyncLimiter

from .exchange import Exchange

_BASE_REST_URL = 'https://api.pro.coinbase.com'
_BASE_WS_URL = 'wss://ws-feed.pro.coinbase.com'

_log = logging.getLogger(__name__)


class Coinbase(Exchange):
    # Capabilities.
    can_stream_balances: bool = False
    can_stream_depth_snapshot: bool = True
    can_margin_trade: bool = False  # TODO: Actually can; need impl
    can_place_market_order: bool = True
    can_place_market_order_quote: bool = True

    def __init__(self, api_key: str, secret_key: str, passphrase: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = base64.b64decode(secret_key)
        self._passphrase = passphrase

        self._ws = CoinbaseFeed(api_key, secret_key, passphrase)
        # TODO: use LRU cache
        self._order_id_to_client_id: dict[str, str] = {}

    async def __aenter__(self) -> Coinbase:
        # Rate limiter.
        # https://help.coinbase.com/en/pro/other-topics/api/faq-on-api
        # The advertised rates do not work, hence we limit to 1 request per second.
        self._pub_limiter = AsyncLimiter(1, 1)  # 3 requests per second, up to 6 in bursts.
        self._priv_limiter = AsyncLimiter(1, 1)  # 5 requests per second, up to 10 in bursts.

        self._session = ClientSession(raise_for_status=False, name=type(self).__name__)
        await self._session.__aenter__()

        await self._ws.__aenter__()

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await self._ws.__aexit__(exc_type, exc, tb)
        await self._session.__aexit__(exc_type, exc, tb)

    async def _paginated_public_request(
        self, method: str, url: str, data: dict[str, Any] = {}
    ) -> AsyncIterable[tuple[ClientResponse, Any]]:
        page_after = None
        while True:
            await self._pub_limiter.acquire()
            if page_after is not None:
                data['after'] = page_after
            response, content = await self._request(method=method, url=url, params=data)
            yield response, content
            page_after = response.headers.get('CB-AFTER')
            if page_after is None:
                break

    async def _public_request(
        self, method: str, url: str, data: dict[str, Any] = {}
    ) -> tuple[ClientResponse, Any]:
        await self._pub_limiter.acquire()
        return await self._request(method=method, url=url, params=data)

    async def _private_request(
        self, method: str, url: str, data: dict[str, Any] = {}
    ) -> tuple[ClientResponse, Any]:
        await self._priv_limiter.acquire()
        timestamp = _auth_timestamp()
        body = json.dumps(data, separators=(',', ':')) if data else ''
        signature = _auth_signature(self._secret_key_bytes, timestamp, method, url, body)
        headers = {
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-KEY': self._api_key,
            'CB-ACCESS-PASSPHRASE': self._passphrase,
            'Content-Type': 'application/json',
        }
        return await self._request(method, url, headers=headers, data=body)

    async def _request(self, method: str, url: str, **kwargs: Any) -> tuple[ClientResponse, Any]:
        async with self._session.request(method, _BASE_REST_URL + url, **kwargs) as response:
            content = await response.json()

        if response.status == 429:
            raise ExchangeException(content['message'])

        return response, content


class CoinbaseFeed:
    def __init__(self, api_key: str, secret_key: str, passphrase: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = base64.b64decode(secret_key)
        self._passphrase = passphrase

        self.session = ClientSession(raise_for_status=True, name=type(self).__name__)
        self.ws_ctx: Optional[AsyncContextManager[ClientWebSocketResponse]] = None
        self.ws: Optional[ClientWebSocketResponse] = None
        self.ws_lock = asyncio.Lock()
        self.process_task: Optional[asyncio.Task] = None

        self.subscriptions_updated: Event[None] = Event(autoclear=True)
        self.subscriptions: dict[str, list[str]] = {}
        self.channels: dict[tuple[str, str], asyncio.Queue] = defaultdict(asyncio.Queue)
        self.type_to_channel: dict[str, str] = {}

    async def __aenter__(self) -> CoinbaseFeed:
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self.process_task)
        if self.ws:
            await self.ws.close()
        if self.ws_ctx:
            await self.ws_ctx.__aexit__(exc_type, exc, tb)
        await self.session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def subscribe(
        self, channel: str, types: list[str], symbols: list[str]
    ) -> AsyncIterator[AsyncIterable[Any]]:
        for type_ in types:
            self.type_to_channel[type_] = channel

        await self._ensure_connection()

        # TODO: Skip subscription if already subscribed. Maybe not a good idea because we may need
        # messages such as depth snapshot again.

        timestamp = _auth_timestamp()
        signature = _auth_signature(self._secret_key_bytes, timestamp, 'GET', '/users/self/verify')
        msg = {
            'type': 'subscribe',
            'product_ids': [_to_product(s) for s in symbols],
            'channels': [channel],
            # To authenticate, we need to add additional fields.
            'signature': signature,
            'key': self._api_key,
            'passphrase': self._passphrase,
            'timestamp': timestamp,
        }

        assert self.ws
        await self.ws.send_json(msg)

        while True:
            if _is_subscribed(self.subscriptions, [channel], symbols):
                break
            await self.subscriptions_updated.wait()

        try:
            yield merge_async(*(stream_queue(self.channels[(channel, s)]) for s in symbols))
        finally:
            # TODO: unsubscribe
            pass

    async def _ensure_connection(self) -> None:
        async with self.ws_lock:
            if self.ws:
                return
            self.ws_ctx = self.session.ws_connect(_BASE_WS_URL)
            self.ws = await self.ws_ctx.__aenter__()
            self.process_task = create_task_sigint_on_exception(self._stream_messages())

    async def _stream_messages(self) -> None:
        assert self.ws
        async for msg in self.ws:
            data = json.loads(msg.data)
            type_ = data['type']
            if type_ == 'subscriptions':
                self.subscriptions.update({
                    c['name']: [_from_product(s) for s in c['product_ids']]
                    for c in data['channels']
                })
                self.subscriptions_updated.set()
            else:
                channel = self.type_to_channel[type_]
                product = _from_product(data['product_id'])
                self.channels[(channel, product)].put_nowait(data)


def _is_subscribed(
    subscriptions: dict[str, list[str]], channels: list[str], symbols: list[str]
) -> bool:
    for channel in channels:
        channel_sub = subscriptions.get(channel)
        if channel_sub is None:
            return False
        for symbol in symbols:
            if symbol not in channel_sub:
                return False
    return True


def to_symbol(symbol: str) -> str:
    return symbol.upper()


def from_symbol(product: str) -> str:
    return product.lower()


def to_interval(interval: int) -> int:
    return interval // 1000


def to_timestamp(timestamp: int) -> str:
    return datetime.utcfromtimestamp(timestamp / 1000.0).isoformat()


def from_timestamp(dt: str) -> int:
    # Format can be either one:
    # - '%Y-%m-%dT%H:%M:%S.%fZ'
    # - '%Y-%m-%dT%H:%M:%SZ'
    dt_format = '%Y-%m-%dT%H:%M:%S.%fZ' if '.' in dt else '%Y-%m-%dT%H:%M:%SZ'
    return datetime_timestamp_ms(
        datetime.strptime(dt, dt_format).replace(tzinfo=UTC)
    )


def _to_decimal(value: Decimal) -> str:
    return f'{value:f}'


def _auth_timestamp() -> str:
    return str(time())


def _auth_signature(
    secret_key: bytes, timestamp: str, method: str, url: str, body: str = ''
) -> str:
    message = (timestamp + method + url + body).encode('ascii')
    signature_hash = hmac.new(secret_key, message, hashlib.sha256).digest()
    return base64.b64encode(signature_hash).decode('ascii')
