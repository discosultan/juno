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
    AssetInfo, BadOrder, Balance, Candle, Depth, ExchangeException, ExchangeInfo, Fees, Fill,
    Filters, OrderMissing, OrderResult, OrderStatus, OrderType, OrderUpdate, Side, Ticker,
    TimeInForce, Trade, json
)
from juno.asyncio import Event, cancel, create_task_sigint_on_exception, merge_async, stream_queue
from juno.filters import Price, Size
from juno.http import ClientResponse, ClientSession, ClientWebSocketResponse
from juno.itertools import page
from juno.math import round_half_up
from juno.time import datetime_timestamp_ms
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import AsyncLimiter, unpack_assets

from .exchange import Exchange

_BASE_REST_URL = 'https://api.pro.coinbase.com'
_BASE_WS_URL = 'wss://ws-feed.pro.coinbase.com'

_log = logging.getLogger(__name__)


class Coinbase(Exchange):
    # Capabilities.
    can_stream_balances: bool = False
    can_stream_depth_snapshot: bool = True
    can_stream_historical_candles: bool = True
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False
    can_list_all_tickers: bool = False
    can_margin_trade: bool = False  # TODO: Actually can; need impl
    can_place_order_market_quote: bool = True

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

    def list_candle_intervals(self) -> list[int]:
        return [
            60000,  # 1m
            300000,  # 5m
            900000,  # 15m
            3600000,  # 1h
            21600000,  # 6h
            86400000,  # 1d
        ]

    async def get_exchange_info(self) -> ExchangeInfo:
        # TODO: Fetch from exchange API if possible? Also has a more complex structure.
        # See https://support.pro.coinbase.com/customer/en/portal/articles/2945310-fees
        fees = {'__all__': Fees(maker=Decimal('0.005'), taker=Decimal('0.005'))}

        _, content = await self._public_request('GET', '/products')
        filters = {}
        for product in content:
            price_step = Decimal(product['quote_increment'])
            size_step = Decimal(product['base_increment'])
            filters[product['id'].lower()] = Filters(
                base_precision=-size_step.normalize().as_tuple()[2],
                quote_precision=-price_step.normalize().as_tuple()[2],
                price=Price(
                    min=Decimal(product['min_market_funds']),
                    max=Decimal(product['max_market_funds']),
                    step=price_step,
                ),
                size=Size(
                    min=Decimal(product['base_min_size']),
                    max=Decimal(product['base_max_size']),
                    step=size_step,
                ),
            )

        return ExchangeInfo(
            assets={'__all__': AssetInfo(precision=8)},
            fees=fees,
            filters=filters,
        )

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        # TODO: Use REST endpoint instead of WS here?
        # https://docs.pro.coinbase.com/#get-product-ticker
        # https://github.com/coinbase/coinbase-pro-node/issues/363#issuecomment-513876145
        if not symbols:
            raise ValueError('Empty symbols list not supported')

        tickers = {}
        async with self._ws.subscribe('ticker', ['ticker'], symbols) as ws:
            async for msg in ws:
                symbol = _from_product(msg['product_id'])
                tickers[symbol] = Ticker(
                    volume=Decimal(msg['volume_24h']),  # TODO: incorrect?!
                    quote_volume=Decimal('0.0'),  # Not supported.
                    price=Decimal(msg['price']),
                )
                if len(tickers) == len(symbols):
                    break
        return tickers

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        result = {}
        if account == 'spot':
            _, content = await self._private_request('GET', '/accounts')
            result['spot'] = {
                b['currency'].lower(): Balance(
                    available=Decimal(b['available']), hold=Decimal(b['hold'])
                ) for b in content
            }
        else:
            raise NotImplementedError()
        return result

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        MAX_CANDLES_PER_REQUEST = 300
        url = f'/products/{_to_product(symbol)}/candles'
        for page_start, page_end in page(start, end, interval, MAX_CANDLES_PER_REQUEST):
            _, content = await self._public_request(
                'GET', url, {
                    'start': _to_datetime(page_start),
                    'end': _to_datetime(page_end - 1),
                    'granularity': _to_granularity(interval)
                }
            )
            for c in reversed(content):
                # This seems to be an issue on Coinbase side. I didn't find any documentation for
                # this behavior but occasionally they send null values inside candle rows for
                # different price fields. Since we want to store all the data and we don't
                # currently use Coinbase for paper or live trading, we simply throw an exception.
                if None in c:
                    raise Exception(f'missing data for candle {c}; please re-run the command')
                yield Candle(
                    c[0] * 1000, Decimal(c[3]), Decimal(c[2]), Decimal(c[1]), Decimal(c[4]),
                    Decimal(c[5]), True
                )

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(
            ws: AsyncIterable[Any]
        ) -> AsyncIterable[Depth.Any]:
            async for data in ws:
                if data['type'] == 'snapshot':
                    yield Depth.Snapshot(
                        bids=[(Decimal(p), Decimal(s)) for p, s in data['bids']],
                        asks=[(Decimal(p), Decimal(s)) for p, s in data['asks']]
                    )
                elif data['type'] == 'l2update':
                    bids = ((p, s) for side, p, s in data['changes'] if side == 'buy')
                    asks = ((p, s) for side, p, s in data['changes'] if side == 'sell')
                    yield Depth.Update(
                        bids=[(Decimal(p), Decimal(s)) for p, s in bids],
                        asks=[(Decimal(p), Decimal(s)) for p, s in asks]
                    )

        async with self._ws.subscribe('level2', ['snapshot', 'l2update'], [symbol]) as ws:
            yield inner(ws)

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        assert account == 'spot'

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            base_asset, quote_asset = unpack_assets(symbol)
            async for data in ws:
                type_ = data['type']
                if type_ == 'received':
                    client_id = data['client_oid']
                    self._order_id_to_client_id[data['order_id']] = client_id
                    yield OrderUpdate.New(
                        client_id=client_id,
                    )
                elif type_ == 'done':
                    reason = data['reason']
                    order_id = data['order_id']
                    client_id = self._order_id_to_client_id[order_id]
                    # TODO: Should be paginated.
                    _, content = await self._private_request('GET', f'/fills?order_id={order_id}')
                    for fill in content:
                        # TODO: Coinbase fee is always returned in quote asset.
                        # TODO: Coinbase does not return quote, so we need to calculate it;
                        # however, we need to know quote precision and rounding rules for that.
                        # TODO: They seem to take fee in addition to specified size (not extract
                        # from size).
                        assert symbol == 'btc-eur'
                        quote_precision = 2
                        base_precision = 8
                        price = Decimal(fill['price'])
                        size = Decimal(fill['size'])
                        fee_quote = round_half_up(Decimal(fill['fee']), quote_precision)
                        fee_size = round_half_up(Decimal(fill['fee']) / price, base_precision)
                        yield OrderUpdate.Match(
                            client_id=client_id,
                            fill=Fill.with_computed_quote(
                                price=price,
                                size=size + fee_size,
                                fee=fee_size if fill['side'] == 'buy' else fee_quote,
                                fee_asset=base_asset if fill['side'] == 'buy' else quote_asset,
                                precision=quote_precision,
                            ),
                        )
                    if reason == 'filled':
                        yield OrderUpdate.Done(
                            time=_from_datetime(data['time']),
                            client_id=client_id,
                        )
                    elif reason == 'canceled':
                        yield OrderUpdate.Cancelled(
                            time=_from_datetime(data['time']),
                            client_id=client_id,
                        )
                    else:
                        raise NotImplementedError(data)
                elif type_ in ['open', 'match']:
                    pass
                else:
                    raise NotImplementedError(data)

        async with self._ws.subscribe(
            'user', ['received', 'open', 'match', 'done'], [symbol]
        ) as ws:
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
        # https://docs.pro.coinbase.com/#place-a-new-order
        if account != 'spot':
            raise NotImplementedError()
        if type_ not in [OrderType.MARKET, OrderType.LIMIT, OrderType.LIMIT_MAKER]:
            # Supports stop orders through params.
            raise NotImplementedError()

        data: dict[str, Any] = {
            'type': 'market' if type_ is OrderType.MARKET else 'limit',
            'side': 'buy' if side is Side.BUY else 'sell',
            'product_id': _to_product(symbol),
        }
        if size is not None:
            data['size'] = _to_decimal(size)
        if quote is not None:
            data['funds'] = _to_decimal(quote)
        if price is not None:
            data['price'] = _to_decimal(price)
        if time_in_force is not None:
            data['time_in_force'] = _to_time_in_force(time_in_force)
        if client_id is not None:
            data['client_oid'] = client_id
        if type_ is OrderType.LIMIT_MAKER:
            data['post_only'] = True

        response, content = await self._private_request('POST', '/orders', data=data)

        if response.status == 400:
            raise BadOrder(content['message'])

        # Does not support returning fills straight away. Need to listen through WS.
        return OrderResult(status=OrderStatus.NEW, time=_from_datetime(content['created_at']))

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        if account != 'spot':
            raise NotImplementedError()
        response, content = await self._private_request('DELETE', f'/orders/client:{client_id}', {
            'product_id': _to_product(symbol),
        })
        if response.status == 404:
            raise OrderMissing(content['message'])

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        trades_desc = []
        async for _, content in self._paginated_public_request(
            'GET', f'/products/{_to_product(symbol)}/trades'
        ):
            done = False
            for val in content:
                time = _from_datetime(val['time'])
                if time >= end:
                    continue
                if time < start:
                    done = True
                    break
                trades_desc.append(Trade(
                    time=time,
                    price=Decimal(val['price']),
                    size=Decimal(val['size'])
                ))
            if done:
                break
        for trade in reversed(trades_desc):
            yield trade

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Trade]:
            async for val in ws:
                if val['type'] == 'last_match':
                    # TODO: Useful for recovery process that downloads missed trades after a dc.
                    continue
                if 'price' not in val or 'size' not in val:
                    continue
                yield Trade(
                    time=_from_datetime(val['time']),
                    price=Decimal(val['price']),
                    size=Decimal(val['size'])
                )

        async with self._ws.subscribe('matches', ['last_match', 'match'], [symbol]) as ws:
            yield inner(ws)

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


def _to_product(symbol: str) -> str:
    return symbol.upper()


def _from_product(product: str) -> str:
    return product.lower()


def _to_granularity(interval: int) -> int:
    return interval // 1000


def _to_datetime(timestamp: int) -> str:
    return datetime.utcfromtimestamp(timestamp / 1000.0).isoformat()


def _from_datetime(dt: str) -> int:
    # Format can be either one:
    # - '%Y-%m-%dT%H:%M:%S.%fZ'
    # - '%Y-%m-%dT%H:%M:%SZ'
    dt_format = '%Y-%m-%dT%H:%M:%S.%fZ' if '.' in dt else '%Y-%m-%dT%H:%M:%SZ'
    return datetime_timestamp_ms(
        datetime.strptime(dt, dt_format).replace(tzinfo=UTC)
    )


def _to_time_in_force(time_in_force: TimeInForce) -> str:
    if time_in_force is TimeInForce.GTC:
        return 'GTC'
    elif time_in_force is TimeInForce.GTT:
        return 'GTT'
    elif time_in_force is TimeInForce.FOK:
        return 'FOK'
    elif time_in_force is TimeInForce.IOC:
        return 'IOC'
    raise NotImplementedError()


def _from_order_status(status: str) -> OrderStatus:
    if status == 'pending':
        return OrderStatus.NEW
    elif status == 'done':
        return OrderStatus.FILLED
    raise NotImplementedError()


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
