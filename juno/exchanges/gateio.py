from __future__ import annotations

import hashlib
import hmac
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from types import TracebackType
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlencode

import juno.json as json
from juno.http import ClientResponse, ClientSession

from .exchange import Exchange

# https://www.gate.io/docs/apiv4/en/index.html#gate-api-v4
_API_URL = 'https://api.gateio.ws'
_WS_URL = 'wss://api.gateio.ws/ws/v4/'


class Session(Exchange):
    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')
        self._session = ClientSession(raise_for_status=False, name=type(self).__name__)

    async def __aenter__(self) -> Session:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> AsyncIterator[ClientResponse]:
        if headers is None:
            headers = {}
        headers.update({'Accept': 'application/json', 'Content-Type': 'application/json'})

        async with self._session.request(
            method=method,
            url=_API_URL + url,
            headers=headers,
            **kwargs,
        ) as response:
            yield response

    @asynccontextmanager
    async def request_signed(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, str]] = None,
    ) -> AsyncIterator[ClientResponse]:
        data = None
        if body is not None:
            data = json.dumps(body, separators=(',', ':'))

        query_string = None
        if params is not None:
            query_string = urlencode(params)

        headers = self._gen_sign(method, url, query_string=query_string, data=data)

        if query_string is not None:
            url += f'?{query_string}'

        async with self.request(method, url, headers, data=data) as response:
            yield response

    async def request_json(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> Any:
        async with self.request(
            method=method,
            url=url,
            headers=headers,
            **kwargs,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def request_signed_json(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, str]] = None,
    ) -> Any:
        async with self.request_signed(method, url, params=params, body=body) as response:
            response.raise_for_status()
            return await response.json()

    def _gen_sign(
        self,
        method: str,
        url: str,
        query_string: Optional[str] = None,
        data: Optional[str] = None,
    ) -> dict[str, str]:
        # https://www.gate.io/docs/apiv4/en/index.html#api-signature-string-generation
        t = time.time()
        m = hashlib.sha512()
        m.update((data or '').encode('utf-8'))
        hashed_payload = m.hexdigest()
        s = f'{method}\n{url}\n{query_string or ""}\n{hashed_payload}\n{t}'
        sign = hmac.new(self._secret_key_bytes, s.encode('utf-8'), hashlib.sha512).hexdigest()
        return {'KEY': self._api_key, 'Timestamp': str(t), 'SIGN': sign}

    def _gen_ws_sign(self, channel: str, event: str, timestamp: int):
        s = f'channel={channel}&event={event}&time={timestamp}'
        sign = hmac.new(self._secret_key_bytes, s.encode('utf-8'), hashlib.sha512).hexdigest()
        return {'method': 'api_key', 'KEY': self._api_key, 'SIGN': sign}


def from_asset(asset: str) -> str:
    return asset.lower()


def from_symbol(symbol: str) -> str:
    return symbol.lower().replace('_', '-')


def to_symbol(symbol: str) -> str:
    return symbol.upper().replace('-', '_')


def to_decimal(value: Decimal) -> str:
    # Converts from scientific notation.
    # 6.4E-7 -> 0.0000_0064
    return f'{value:f}'
