from __future__ import annotations

import hashlib
import hmac
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from types import TracebackType
from typing import Any, AsyncIterable, AsyncIterator, Optional
from urllib.parse import urlencode

import juno.json as json
from juno.common import (
    Balance, Candle, Depth, ExchangeInfo, Fees, Fill, Filters, OrderResult, OrderStatus, OrderType,
    OrderUpdate, Side, TimeInForce
)
from juno.errors import OrderMissing, OrderWouldBeTaker
from juno.filters import Price, Size
from juno.http import ClientResponse, ClientSession
from juno.utils import short_uuid4

from .exchange import Exchange

# https://www.gate.io/docs/apiv4/en/index.html#gate-api-v4
_API_URL = 'https://api.gateio.ws'
_WS_URL = 'wss://api.gateio.ws/ws/v4/'


class GateIO(Exchange):
    def __init__(self, api_key: str, secret_key: str, high_precision: bool = True) -> None:
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')
        self._high_precision = high_precision
        self._session = ClientSession(raise_for_status=False, name=type(self).__name__)

    @staticmethod
    def generate_client_id() -> str:
        return short_uuid4()

    async def __aenter__(self) -> GateIO:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_exchange_info(self) -> ExchangeInfo:
        # https://www.gate.io/docs/apiv4/en/index.html#list-all-currency-pairs-supported
        content = await self._request_json('GET', '/api/v4/spot/currency_pairs')

        fees, filters = {}, {}
        for pair in (c for c in content if c['trade_status'] == 'tradable'):
            symbol = _from_symbol(pair['id'])
            # TODO: Take into account different fee levels. Currently only worst level.
            fee = Decimal(pair['fee']) / 100
            fees[symbol] = Fees(maker=fee, taker=fee)
            filters[symbol] = Filters(
                base_precision=pair['precision'],
                quote_precision=pair['amount_precision'],
                size=Size(
                    min=(
                        Decimal('0.0') if (min_base_amount := pair.get('min_base_amount')) is None
                        else Decimal(min_base_amount)
                    ),
                ),
                price=Price(
                    min=(
                        Decimal('0.0')
                        if (min_quote_amount := pair.get('min_quote_amount')) is None
                        else Decimal(min_quote_amount)
                    ),
                )
            )

        return ExchangeInfo(
            fees=fees,
            filters=filters,
        )

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        # https://www.gate.io/docs/apiv4/en/index.html#retrieve-order-book
        content = await self._request_json(
            'GET',
            '/api/v4/spot/order_book',
            params={'currency_pair': _to_symbol(symbol)},
        )
        return Depth.Snapshot(
            asks=[(Decimal(price), Decimal(size)) for price, size in content['asks']],
            bids=[(Decimal(price), Decimal(size)) for price, size in content['bids']],
        )

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        channel = 'spot.order_book_update'

        # https://www.gateio.pro/docs/apiv4/ws/index.html#changed-order-book-levels
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Update]:
            async for msg in ws:
                data = json.loads(msg.data)

                if data['channel'] != channel or data['event'] != 'update':
                    continue

                data = data['result']
                yield Depth.Update(
                    bids=[(Decimal(price), Decimal(size)) for price, size in data['b']],
                    asks=[(Decimal(price), Decimal(size)) for price, size in data['a']],
                    first_id=data['U'],
                    last_id=data['u'],
                )

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            await ws.send_json({
                'time': int(time.time()),
                'channel': channel,
                'event': 'subscribe',  # 'unsubscribe' for unsubscription
                'payload': [_to_symbol(symbol), '100ms' if self._high_precision else '1000ms'],
            })
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
        assert account == 'spot'
        assert time_in_force is None
        assert quote is None
        assert size is not None
        # assert price is not None  # Required by doc but what about marker order?

        body: dict[str, Any] = {
            'currency_pair': _to_symbol(symbol),
            'type': _to_order_type(type_),
            'side': _to_side(side),
            'time_in_force': _to_time_in_force(type_),
            # 'price': _to_decimal(price),
            'amount': _to_decimal(size),
        }
        if client_id is not None:
            body['text'] = f't-{client_id}'
        if price is not None:
            body['price'] = _to_decimal(price),
        content = await self._request_signed_json('POST', '/api/v4/spot/orders', body=body)

        if content['status'] == 'cancelled':
            raise OrderWouldBeTaker()

        return OrderResult(
            time=int(content['createTime']) * 1000,
            status=OrderStatus.NEW,
        )

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        # NB! Custom client id will not be available anymore if the order has been up for more than
        # 30 min.
        assert account == 'spot'

        params = {
            'currency_pair': _to_symbol(symbol),
        }

        async with self._request_signed(
            'DELETE',
            f'/api/v4/spot/orders/{client_id}',
            params=params,
        ) as response:
            if response.status == 400:
                content = await response.json()
                raise OrderMissing(content['message'])

            response.raise_for_status()

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        assert account == 'spot'
        channel = 'spot.orders'

        # https://www.gateio.pro/docs/apiv4/ws/index.html#client-subscription-7
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            async for msg in ws:
                data = json.loads(msg.data)
                event = data['event']

                if data['channel'] != channel or event not in ['put', 'update', 'finish']:
                    continue

                data = data['result']
                client_id = data['text'][2:]
                if event == 'put':
                    yield OrderUpdate.New(client_id=client_id)
                elif event == 'update':
                    yield OrderUpdate.Match(
                        client_id=client_id,
                        fill=Fill(
                            price=Decimal(data['price']),
                            size=Decimal(data['amount']),
                            fee=Decimal(data['fee']),
                            fee_asset=data['fee_currency'].lower(),
                        ),
                    )
                elif event == 'finish':
                    time = data['update_time'] * 1000
                    if data['left'] == '0':
                        yield OrderUpdate.Done(
                            client_id=client_id,
                            time=time,
                        )
                    else:
                        yield OrderUpdate.Cancelled(
                            client_id=client_id,
                            time=time,
                        )
                else:
                    raise NotImplementedError()

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            time_sec = int(time.time())
            event = 'subscribe'  # 'unsubscribe' for unsubscription
            await ws.send_json({
                'time': time_sec,
                'channel': channel,
                'event': event,
                'payload': [_to_symbol(symbol)],  # Can pass '!all' for all symbols.
                'auth': self._gen_ws_sign(channel, event, time_sec),
            })
            yield inner(ws)

    @asynccontextmanager
    async def _request(
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
    async def _request_signed(
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

        async with self._request(method, url, headers, data=data) as response:
            yield response

    async def _request_json(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> Any:
        async with self._request(
            method=method,
            url=url,
            headers=headers,
            **kwargs,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def _request_signed_json(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, str]] = None,
    ) -> Any:
        async with self._request_signed(method, url, params=params, body=body) as response:
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

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        assert account == 'spot'
        raise NotImplementedError()
        # result = {}
        # _, content = await self._api_request(
        #     'GET', '/api/v3/account', weight=5, security=_SEC_USER_DATA
        # )
        # result['spot'] = {
        #     b['asset'].lower(): Balance(
        #         available=Decimal(b['free']),
        #         hold=Decimal(b['locked']),
        #     )
        #     for b in content['balances']
        # }
        # return result

    def map_candle_intervals(self) -> dict[int, int]:
        raise NotImplementedError()
        # return {
        #     60000: 0,  # 1m
        #     180000: 0,  # 3m
        #     300000: 0,  # 5m
        #     900000: 0,  # 15m
        #     1800000: 0,  # 30m
        #     3600000: 0,  # 1h
        #     7200000: 0,  # 2h
        #     14400000: 0,  # 4h
        #     21600000: 0,  # 6h
        #     28800000: 0,  # 8h
        #     43200000: 0,  # 12h
        #     86400000: 0,  # 1d
        #     259200000: 0,  # 3d
        #     604800000: 345600000,  # 1w 4d
        #     2629746000: 2541726000,  # 1M 4w1d10h2m6s
        # }

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        raise NotImplementedError()
        # limit = 1000  # Max possible candles per request.
        # binance_interval = strfinterval(interval)
        # binance_symbol = _to_http_symbol(symbol)
        # # Start 0 is a special value indicating that we try to find the earliest available candle.
        # pagination_interval = interval
        # if start == 0:
        #     pagination_interval = end - start
        # for page_start, page_end in page(start, end, pagination_interval, limit):
        #     _, content = await self._api_request(
        #         'GET',
        #         '/api/v3/klines',
        #         data={
        #             'symbol': binance_symbol,
        #             'interval': binance_interval,
        #             'startTime': page_start,
        #             'endTime': page_end - 1,
        #             'limit': limit
        #         }
        #     )
        #     for c in content:
        #         # Binance can return bad candles where the time does not fall within the requested
        #         # interval. For example, the second candle of the following query has bad time:
        #         # https://api.binance.com/api/v1/klines?symbol=ETHBTC&interval=4h&limit=10&startTime=1529971200000&endTime=1530000000000
        #         yield Candle(
        #             c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
        #             Decimal(c[5]), True
        #         )


def _from_symbol(symbol: str) -> str:
    return symbol.lower().replace('_', '-')


def _to_symbol(symbol: str) -> str:
    return symbol.upper().replace('-', '_')


def _to_order_type(type: OrderType) -> str:
    if type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]:
        # We control the order behavior through TimeInForce instead.
        return 'limit'
    raise NotImplementedError()


def _to_time_in_force(type: OrderType) -> str:
    if type is OrderType.LIMIT:
        return 'gtc'
    if type is OrderType.LIMIT_MAKER:
        return 'poc'
    if type is OrderType.MARKET:
        return 'ioc'
    raise NotImplementedError()


def _to_side(side: Side) -> str:
    if side is Side.BUY:
        return 'buy'
    if side is Side.SELL:
        return 'sell'
    raise NotImplementedError()


def _to_decimal(value: Decimal) -> str:
    # Converts from scientific notation.
    # 6.4E-7 -> 0.0000_0064
    return f'{value:f}'
