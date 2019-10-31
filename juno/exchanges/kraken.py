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
    OrderType, OrderUpdate, Side, SymbolsInfo, TimeInForce
)
from juno.asyncio import Event, cancel, cancelable
from juno.http import ClientSession, ClientWebSocketResponse
from juno.time import time_ms
from juno.typing import ExcType, ExcValue, Traceback

from .exchange import Exchange

_API_URL = 'https://api.kraken.com'

# https://docs.kraken.com/websockets/
# https://support.kraken.com/hc/en-us/articles/360022326871-Public-WebSockets-API-common-questions
_PUBLIC_WS_URL = 'wss://ws.kraken.com'
_PRIVATE_WS_URL = 'wss://ws-auth.kraken.com'

_log = logging.getLogger(__name__)


class Kraken(Exchange):
    def __init__(self, api_key: str, secret_key: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._decoded_secret_key = base64.b64decode(secret_key)

    async def __aenter__(self) -> Kraken:
        # TODO: concurrently
        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()
        self._public_ws = KrakenTopic(_PUBLIC_WS_URL)
        await self._public_ws.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await self._public_ws.__aexit__(exc_type, exc, tb)
        await self._session.__aexit__(exc_type, exc, tb)

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
        yield  # type: ignore

    async def get_depth(self, symbol: str) -> DepthSnapshot:
        raise NotImplementedError()

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Union[DepthSnapshot, DepthUpdate]]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Any]:
            async for msg in ws:
                for val in msg:
                    _log.critical(msg)
                    yield True

        async with self._public_ws.subscribe([_symbol(symbol)], {
            'name': 'book',
            'depth': 10,
        }) as subscription:
            yield inner(subscription)

    @asynccontextmanager
    async def connect_stream_orders(self) -> AsyncIterator[AsyncIterable[OrderUpdate]]:
        yield  # type: ignore

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
        async with self._session.request(
            method=method, url=_API_URL + url, data=data, headers=headers
        ) as res:
            result = await res.json(loads=json.loads)
            errors = result['error']
            if len(errors) > 0:
                raise Exception(errors)
            return result


class KrakenTopic:
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

    async def __aenter__(self) -> KrakenTopic:
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
        self, pairs: List[str], subscription: Any
    ) -> AsyncIterator[AsyncIterable[Any]]:
        await self._ensure_connection()
        assert self.ws

        reqid = self.reqid
        subscribed = self.subscriptions[reqid]
        self.reqid += 1
        await self.ws.send_json({
            'event': 'subscribe',
            'reqid': reqid,
            'pair': pairs,
            'subscription': subscription,
        })

        received = await subscribed.wait()

        async def inner() -> AsyncIterable[Any]:
            while True:
                yield await received.wait()

        try:
            yield inner()
        finally:
            # TODO: unsubscribe
            pass

    async def _ensure_connection(self) -> None:
        async with self.ws_lock:
            if self.ws:
                return

            self.ws_ctx = self.session.ws_connect(self.url)
            self.ws = await self.ws_ctx.__aenter__()

            self.process_task = asyncio.create_task(cancelable(self._process()))

    async def _process(self) -> None:
        assert self.ws
        async for msg in self.ws:
            data = json.loads(msg.data)
            if isinstance(data, dict):
                if data['event'] == 'subscriptionStatus':
                    subscribed = self.subscriptions[data['reqid']]
                    received = self.channels[data['channelID']]
                    subscribed.set(received)
            else:  # List.
                channel_id = data[0]
                type_data = data[1:len(data)-2]
                # type_ = data[-2]
                # pair = data[-1]
                self.channels[channel_id].set(type_data)  # type: ignore


def _symbol(symbol: str) -> str:
    return symbol.replace('-', '/').upper()
