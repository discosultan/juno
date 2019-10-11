from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import urllib.parse
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterator, AsyncIterable, Dict, Optional, Union

import simplejson as json

from juno import (
    Balance, CancelOrderResult, Candle, DepthSnapshot, DepthUpdate, Fees, Filters, OrderResult,
    OrderType, OrderUpdate, Side, SymbolsInfo, TimeInForce
)
from juno.http import ClientSession
from juno.time import time_ms
from juno.typing import ExcType, ExcValue, Traceback

from .exchange import Exchange

_BASE_URL = 'https://api.kraken.com'

_log = logging.getLogger(__name__)


class Kraken(Exchange):
    def __init__(self, api_key: str, secret_key: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._decoded_secret_key = base64.b64decode(secret_key)

    async def __aenter__(self) -> Kraken:
        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
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
        yield  # type: ignore

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
            method=method, url=_BASE_URL + url, data=data, headers=headers
        ) as res:
            result = await res.json(loads=json.loads)
            errors = result['error']
            if len(errors) > 0:
                raise Exception(errors)
            return result
