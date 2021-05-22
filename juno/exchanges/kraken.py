from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import urllib.parse
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncContextManager, AsyncIterable, AsyncIterator, Optional

from juno import Balance, Depth, OrderResult, OrderType, OrderUpdate, Side, TimeInForce, json
from juno.asyncio import Event, cancel, create_task_sigint_on_exception, stream_queue
from juno.http import ClientSession, ClientWebSocketResponse
from juno.time import time_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import AsyncLimiter, unpack_assets

from .exchange import Exchange

# https://www.kraken.com/features/api
_API_URL = 'https://api.kraken.com'

# https://docs.kraken.com/websockets/
# https://support.kraken.com/hc/en-us/articles/360022326871-Public-WebSockets-API-common-questions
_PUBLIC_WS_URL = 'wss://ws.kraken.com'
_PRIVATE_WS_URL = 'wss://ws-auth.kraken.com'


class Kraken(Exchange):
    # Capabilities.
    can_stream_balances: bool = False
    can_stream_depth_snapshot: bool = True
    can_list_all_tickers: bool = False
    can_margin_trade: bool = False  # TODO: Actually can; need impl
    can_place_market_order: bool = True
    can_place_market_order_quote: bool = False  # TODO: Can but only for non-leveraged orders

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._decoded_secret_key = base64.b64decode(secret_key)

    async def __aenter__(self) -> Kraken:
        # Rate limiters.
        # TODO: This is Starter rate. The rate differs for Intermediate and Pro users.
        self._reqs_limiter = AsyncLimiter(15, 45)
        self._order_placing_limiter = AsyncLimiter(1, 1)

        self._session = ClientSession(raise_for_status=True, name=type(self).__name__)
        await self._session.__aenter__()

        self.public_ws = KrakenPublicFeed(_PUBLIC_WS_URL)
        self._private_ws = KrakenPrivateFeed(_PRIVATE_WS_URL, self)
        await asyncio.gather(
            self.public_ws.__aenter__(),
            self._private_ws.__aenter__(),
        )

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(
            self._private_ws.__aexit__(exc_type, exc, tb),
            self.public_ws.__aexit__(exc_type, exc, tb),
        )
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        result = {}
        if account == 'spot':
            res = await self._request_private('/0/private/Balance')
            result['spot'] = {
                a[1:].lower(): Balance(available=Decimal(v), hold=Decimal('0.0'))
                for a, v in res['result'].items()
                if len(a) == 4 and a[0] in ['X', 'Z']
            }
        else:
            raise NotImplementedError()
        return result

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Any]:
            async for val in ws:
                if 'as' in val or 'bs' in val:
                    bids = val.get('bs', [])
                    asks = val.get('as', [])
                    yield Depth.Snapshot(
                        bids=[(Decimal(u[0]), Decimal(u[1])) for u in bids],
                        asks=[(Decimal(u[0]), Decimal(u[1])) for u in asks],
                    )
                else:
                    bids = val.get('b', [])
                    asks = val.get('a', [])
                    yield Depth.Update(
                        bids=[(Decimal(u[0]), Decimal(u[1])) for u in bids],
                        asks=[(Decimal(u[0]), Decimal(u[1])) for u in asks],
                    )

        async with self.public_ws.subscribe({
            'name': 'book',
            'depth': 10,
        }, [to_ws_symbol(symbol)]) as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str,
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        assert account == 'spot'

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            async for o in ws:
                # TODO: map
                yield o

        async with self._private_ws.subscribe({'name': 'openOrders'}) as ws:
            yield inner(ws)

    async def place_order(
        self,
        account: str,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
    ) -> OrderResult:
        # TODO: use order placing limiter instead of default.
        pass

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        pass

    async def _get_websockets_token(self) -> str:
        res = await self._request_private('/0/private/GetWebSocketsToken')
        return res['result']['token']

    async def request_public(
        self, method: str, url: str, data: Optional[Any] = None, cost: int = 1
    ) -> Any:
        data = data or {}
        return await self._request(method, url, data, {}, self._reqs_limiter, cost)

    async def _request_private(
        self,
        url: str,
        data: Optional[Any] = None,
        cost: int = 1,
        limiter: Optional[AsyncLimiter] = None
    ) -> Any:
        if limiter is None:
            limiter = self._reqs_limiter

        data = data or {}
        nonce = time_ms()
        data['nonce'] = nonce
        # TODO: support OTP
        # if enabled:
        #   data['otp] = 'password'

        querystr = urllib.parse.urlencode(data)
        encoded = (str(nonce) + querystr).encode()
        message = url.encode() + hashlib.sha256(encoded).digest()
        signature = hmac.new(self._decoded_secret_key, message, hashlib.sha512)

        headers = {
            'API-Key': self._api_key,
            'API-Sign': base64.b64encode(signature.digest()).decode()
        }
        return await self._request('POST', url, data, headers, limiter, cost)

    async def _request(
        self, method: str, url: str, data: dict[str, Any], headers: dict[str, str],
        limiter: AsyncLimiter, cost: int
    ) -> Any:
        if limiter is None:
            limiter = self._reqs_limiter
        if cost > 0:
            await limiter.acquire(cost)

        kwargs = {
            'method': method,
            'url': _API_URL + url,
            'headers': headers,
        }
        kwargs['params' if method == 'GET' else 'data'] = data

        async with self._session.request(**kwargs) as res:
            result = await res.json()
            errors = result['error']
            if len(errors) > 0:
                raise Exception(errors)
            return result


class KrakenPublicFeed:
    def __init__(self, url: str) -> None:
        self.url = url

        self.session = ClientSession(raise_for_status=True, name=type(self).__name__)
        self.ws_ctx: Optional[AsyncContextManager[ClientWebSocketResponse]] = None
        self.ws: Optional[ClientWebSocketResponse] = None
        self.ws_lock = asyncio.Lock()
        self.process_task: Optional[asyncio.Task] = None

        self.reqid = 1
        self.subscriptions: dict[int, Event[asyncio.Queue[Any]]] = defaultdict(
            lambda: Event(autoclear=True)
        )
        self.channels: dict[int, asyncio.Queue[Any]] = defaultdict(asyncio.Queue)

    async def __aenter__(self) -> KrakenPublicFeed:
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
        self, subscription: Any, symbols: Optional[list[str]] = None
    ) -> AsyncIterator[AsyncIterable[Any]]:
        await self._ensure_connection()

        reqid = self.reqid
        subscribed = self.subscriptions[reqid]
        self.reqid += 1
        payload = {
            'event': 'subscribe',
            'reqid': reqid,
            'subscription': subscription,
        }
        if symbols is not None:
            payload['pair'] = symbols

        await self._send(payload)

        received = await subscribed.wait()

        try:
            yield stream_queue(received)
        finally:
            # TODO: unsubscribe
            pass

    async def _send(self, msg: Any) -> None:
        assert self.ws
        await self.ws.send_json(msg)

    async def _ensure_connection(self) -> None:
        async with self.ws_lock:
            if self.ws:
                return
            await self._connect()

    async def _connect(self) -> None:
        self.ws_ctx = self.session.ws_connect(self.url)
        self.ws = await self.ws_ctx.__aenter__()
        self.process_task = create_task_sigint_on_exception(self._stream_messages())

    async def _stream_messages(self) -> None:
        assert self.ws
        async for msg in self.ws:
            data = json.loads(msg.data)
            self._process_message(data)

    def _process_message(self, data: Any) -> None:
        if isinstance(data, dict):
            if data['event'] == 'subscriptionStatus':
                _validate_subscription_status(data)
                subscribed = self.subscriptions[data['reqid']]
                received = self.channels[data['channelID']]
                subscribed.set(received)
        else:  # List.
            channel_id = data[0]

            if len(data) > 4:
                # Consolidate.
                val: Any = {}
                for consolidate in data[1:len(data) - 2]:
                    val.update(consolidate)
            else:
                val = data[1]

            # type_ = data[-2]
            # pa_onir = data[-1]
            self.channels[channel_id].put_nowait(val)  # type: ignore


class KrakenPrivateFeed(KrakenPublicFeed):
    def __init__(self, url: str, kraken: Kraken) -> None:
        super().__init__(url)
        self.kraken = kraken

    async def _connect(self) -> None:
        _, token = await asyncio.gather(super()._connect(), self.kraken._get_websockets_token())
        self.token = token

    async def _send(self, payload: Any) -> None:
        payload['subscription']['token'] = self.token
        await super()._send(payload)

    def _process_message(self, data: Any) -> None:
        if isinstance(data, dict):
            if data['event'] == 'subscriptionStatus':
                _validate_subscription_status(data)
                subscribed = self.subscriptions[data['reqid']]
                received = self.channels[data['channelName']]
                subscribed.set(received)
        else:  # List.
            channel_id = data[1]
            self.channels[channel_id].put_nowait(data[0])  # type: ignore


def _validate_subscription_status(data: Any) -> None:
    if data['status'] == 'error':
        raise Exception(data['errorMessage'])


def from_http_timestamp(time: Decimal) -> int:
    # Convert seconds to milliseconds.
    return int(time * 1000)


def from_ws_timestamp(time: str) -> int:
    # Convert seconds to milliseconds.
    return int(Decimal(time) * 1000)


def to_http_timestamp(time: int) -> int:
    # Convert milliseconds to nanoseconds.
    return time * 1_000_000


def to_ws_symbol(symbol: str) -> str:
    return symbol.replace('-', '/').upper()


ASSET_ALIAS_MAP = {
    'btc': 'xbt',
    'doge': 'xdg',
}
REVERSE_ASSET_ALIAS_MAP = {v: k for k, v in ASSET_ALIAS_MAP.items()}


def to_http_symbol(symbol: str) -> str:
    base, quote = unpack_assets(symbol)
    return f'{ASSET_ALIAS_MAP.get(base, base)}{ASSET_ALIAS_MAP.get(quote, quote)}'


def from_http_symbol(symbol: str) -> str:
    base, quote = unpack_assets(symbol)
    return f'{REVERSE_ASSET_ALIAS_MAP.get(base, base)}-{REVERSE_ASSET_ALIAS_MAP.get(quote, quote)}'
