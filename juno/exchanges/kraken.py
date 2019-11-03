from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import urllib.parse
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import (
    Any, AsyncContextManager, AsyncIterable, AsyncIterator, Dict, List, Optional, Union
)

import juno.json as json
from juno import (
    Balance, CancelOrderResult, Candle, DepthSnapshot, DepthUpdate, Fees, Filters, OrderResult,
    OrderType, OrderUpdate, Side, SymbolsInfo, TimeInForce, Trade
)
from juno.asyncio import Event, cancel, cancelable
from juno.http import ClientSession, ClientWebSocketResponse
from juno.time import time_ms, MIN_MS
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import unpack_symbol

from .exchange import Exchange

# https://www.kraken.com/features/api
_API_URL = 'https://api.kraken.com'

# https://docs.kraken.com/websockets/
# https://support.kraken.com/hc/en-us/articles/360022326871-Public-WebSockets-API-common-questions
_PUBLIC_WS_URL = 'wss://ws.kraken.com'
_PRIVATE_WS_URL = 'wss://ws-auth.kraken.com'

_log = logging.getLogger(__name__)


class Kraken(Exchange):
    def __init__(self, api_key: str, secret_key: str) -> None:
        super().__init__(depth_ws_snapshot=True)
        self._api_key = api_key
        self._decoded_secret_key = base64.b64decode(secret_key)

    async def __aenter__(self) -> Kraken:
        self._session = ClientSession(raise_for_status=True)
        self._public_ws = KrakenPublicTopic(_PUBLIC_WS_URL)
        self._private_ws = KrakenPrivateTopic(_PRIVATE_WS_URL, self)
        await asyncio.gather(
            self._session.__aenter__(),
            self._public_ws.__aenter__(),
            self._private_ws.__aenter__(),
        )
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(
            self._private_ws.__aexit__(exc_type, exc, tb),
            self._public_ws.__aexit__(exc_type, exc, tb),
            self._session.__aexit__(exc_type, exc, tb),
        )

    async def get_symbols_info(self) -> SymbolsInfo:
        res = await self._request_public('GET', '/0/public/AssetPairs')
        fees, filters = {}, {}
        for val in res['result'].values():
            name = f'{val["base"][1:].lower()}-{val["quote"][1:].lower()}'
            # TODO: Take into account different fee levels. Currently only worst level.
            taker_fee = val['fees'][0][1]
            maker_fees = val.get('fees_maker')
            fees[name] = Fees(maker=maker_fees[0][1] if maker_fees else taker_fee, taker=taker_fee)
            filters[name] = Filters(
                base_precision=val['lot_decimals'],
                quote_precision=val['pair_decimals'],
            )
        return SymbolsInfo(fees=fees, filters=filters)

    async def get_balances(self) -> Dict[str, Balance]:
        res = await self._request_private('/0/private/Balance')
        result = {}
        for asset, available in res['result'].items():
            if len(asset) == 4 and asset[0] in ['X', 'Z']:
                asset = asset[1:]
            result[asset.lower()] = Balance(available=Decimal(available), hold=Decimal(0))
        return result

    @asynccontextmanager
    async def connect_stream_balances(self) -> AsyncIterator[AsyncIterable[Dict[str, Balance]]]:
        yield  # type: ignore

    async def stream_historical_candles(self, symbol: str, interval: int, start: int,
                                        end: int) -> AsyncIterable[Candle]:
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_candles(self, symbol: str,
                                     interval: int) -> AsyncIterator[AsyncIterable[Candle]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Candle]:
            async for c in ws:
                # TODO: Kraken doesn't publish candles for intervals where there are no trades.
                # We should fill those caps ourselves.
                # They also send multiple candles per interval. We need to determine when a candle
                # is closed ourselves. Trickier than with Binance.
                yield Candle(
                    # They provide end and not start time, hence we subtract interval.
                    time=int(Decimal(c[1]) * 1000) - interval,
                    open=Decimal(c[2]),
                    high=Decimal(c[3]),
                    low=Decimal(c[4]),
                    close=Decimal(c[5]),
                    volume=Decimal(c[7]),
                    closed=True,
                )

        async with self._public_ws.subscribe({
            'name': 'ohlc',
            'interval': interval // MIN_MS
        }, [_ws_symbol(symbol)]) as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Union[DepthSnapshot, DepthUpdate]]]:
        async def inner(
            ws: AsyncIterable[Any]
        ) -> AsyncIterable[Union[DepthSnapshot, DepthUpdate]]:
            async for val in ws:
                if 'as' in val or 'bs' in val:
                    bids = val.get('bs', [])
                    asks = val.get('as', [])
                    yield DepthSnapshot(
                        bids=[(Decimal(u[0]), Decimal(u[1])) for u in bids],
                        asks=[(Decimal(u[0]), Decimal(u[1])) for u in asks],
                    )
                else:
                    bids = val.get('b', [])
                    asks = val.get('a', [])
                    yield DepthUpdate(
                        bids=[(Decimal(u[0]), Decimal(u[1])) for u in bids],
                        asks=[(Decimal(u[0]), Decimal(u[1])) for u in asks],
                    )

        async with self._public_ws.subscribe({
            'name': 'book',
            'depth': 10,
        }, [_ws_symbol(symbol)]) as subscription:
            yield inner(subscription)

    @asynccontextmanager
    async def connect_stream_orders(self) -> AsyncIterator[AsyncIterable[OrderUpdate]]:
        async def inner(
            ws: AsyncIterable[Any]
        ) -> AsyncIterable[OrderUpdate]:
            async for o in ws:
                # TODO: map
                yield o

        async with self._private_ws.subscribe({'name': 'openOrders'}) as subscription:
            yield inner(subscription)

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
        pass

    async def cancel_order(self, symbol: str, client_id: str) -> CancelOrderResult:
        pass

    async def stream_historical_trades(self, symbol: str, start: int,
                                       end: int) -> AsyncIterable[Trade]:
        since = _time(start)
        while True:
            res = await self._request_public(
                'GET',
                '/0/public/Trades',
                {'pair': _symbol(symbol), 'since': since}
            )
            result = res['result']
            since = result['last']
            _, trades = next(iter(result.items()))
            for trade in trades:
                time = _from_time(trade[2])
                if time >= end:
                    return
                yield Trade(
                    time=time,
                    price=Decimal(trade[0]),
                    size=Decimal(trade[1]),
                )

    async def _get_websockets_token(self) -> str:
        res = await self._request_private('/0/private/GetWebSocketsToken')
        return res['result']['token']

    def _request_public(self, method: str, url: str, data: Optional[Any] = None):
        data = data or {}
        return self._request(method, url, data)

    def _request_private(self, url: str, data: Optional[Any] = None):
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
        return self._request('POST', url, data, headers)

    async def _request(
        self, method: str, url: str, data: Dict[str, Any], headers: Dict[str, str] = {}
    ):
        kwargs = {
            'method': method,
            'url': _API_URL + url,
            'headers': headers,
        }
        kwargs['params' if method == 'GET' else 'data'] = data
        async with self._session.request(**kwargs) as res:
            result = await res.json(loads=json.loads)
            errors = result['error']
            if len(errors) > 0:
                raise Exception(errors)
            return result


class KrakenPublicTopic:
    def __init__(self, url: str) -> None:
        self.url = url

        self.session = ClientSession(raise_for_status=True)
        self.ws_ctx: Optional[AsyncContextManager[ClientWebSocketResponse]] = None
        self.ws: Optional[ClientWebSocketResponse] = None
        self.ws_lock = asyncio.Lock()
        self.process_task: Optional[asyncio.Task] = None

        self.reqid = 1
        self.subscriptions: Dict[int, Event[Event[Any]]] = defaultdict(
            lambda: Event(autoclear=True)
        )
        self.channels: Dict[int, Event[Any]] = defaultdict(lambda: Event(autoclear=True))

    async def __aenter__(self) -> KrakenPublicTopic:
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
        self, subscription: Any, pairs: Optional[List[str]] = None
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
        if pairs is not None:
            payload['pair'] = pairs

        await self._send(payload)

        received = await subscribed.wait()

        async def inner() -> AsyncIterable[Any]:
            while True:
                yield await received.wait()

        try:
            yield inner()
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
        self.process_task = asyncio.create_task(cancelable(self._stream_messages()))

    async def _stream_messages(self) -> None:
        assert self.ws
        async for msg in self.ws:
            data = json.loads(msg.data)
            self._process_message(data)

    def _process_message(self, data: Any) -> None:
        if isinstance(data, dict):
            if data['event'] == 'subscriptionStatus':
                subscribed = self.subscriptions[data['reqid']]
                received = self.channels[data['channelID']]
                subscribed.set(received)
        else:  # List.
            channel_id = data[0]

            if len(data) > 4:
                # Consolidate.
                val: Any = {}
                for consolidate in data[1:len(data)-2]:
                    val.update(consolidate)
            else:
                val = data[1]

            # type_ = data[-2]
            # pa_onir = data[-1]
            self.channels[channel_id].set(val)  # type: ignore


class KrakenPrivateTopic(KrakenPublicTopic):
    def __init__(self, url: str, kraken: Kraken) -> None:
        super().__init__(url)
        self.kraken = kraken

    async def _connect(self) -> None:
        _, token = await asyncio.gather(
            super()._connect(),
            self.kraken._get_websockets_token()
        )
        self.token = token

    async def _send(self, payload: Any) -> None:
        payload['subscription']['token'] = self.token
        await super()._send(payload)

    def _process_message(self, data: Any) -> None:
        if isinstance(data, dict):
            if data['event'] == 'subscriptionStatus':
                subscribed = self.subscriptions[data['reqid']]
                received = self.channels[data['channelName']]
                subscribed.set(received)
        else:  # List.
            channel_id = data[1]
            self.channels[channel_id].set(data[0])  # type: ignore


def _from_time(time: int) -> int:
    # Convert seconds to milliseconds.
    return int(time * 1000)


def _time(time: int) -> int:
    # Convert milliseconds to nanoseconds.
    return time * 1000


def _ws_symbol(symbol: str) -> str:
    return symbol.replace('-', '/').upper()


def _symbol(symbol: str) -> str:
    base, quote = unpack_symbol(symbol)
    return f'{_substitute_alias(base)}{_substitute_alias(quote)}'


def _substitute_alias(asset: str) -> str:
    return {
        'btc': 'xbt',
        'doge': 'xdg',
    }.get(asset, asset)
