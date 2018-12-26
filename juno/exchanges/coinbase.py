import base64
from datetime import datetime
import hashlib
import hmac
import json
from time import time

from juno import Balance, Candle, SymbolInfo
from juno.http import ClientSession
from juno.math import floor_multiple
from juno.time import time_ms
from juno.utils import LeakyBucket, page


_BASE_REST_URL = 'https://api.pro.coinbase.com'
_BASE_WS_URL = 'wss://ws-feed.pro.coinbase.com'


class Coinbase:

    def __init__(self, api_key: str, secret_key: str, passphrase: str):
        self._session = None
        self._api_key = api_key
        self._secret_key_bytes = base64.b64decode(secret_key)
        self._passphrase = passphrase

        # Rate limiter.
        self._pub_limiter = LeakyBucket(rate=1, period=1)   # They advertise 3 per sec.
        self._priv_limiter = LeakyBucket(rate=5, period=1)  # They advertise 5 per sec.

    async def __aenter__(self):
        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_symbol_infos(self):
        res = await self._public_request('GET', '/products')
        result = {}
        for product in res:
            result[product['id'].lower()] = SymbolInfo(
                min_size=float(product['base_min_size']),
                max_size=float(product['base_max_size']),
                size_step=float(product['base_min_size']),
                min_price=float(product['min_market_funds']),
                max_price=float(product['max_market_funds']),
                price_step=float(product['quote_increment']))
        return result

    async def stream_balances(self):
        res = await self._private_request('GET', '/accounts')
        result = {}
        for balance in res:
            result[balance['currency'].lower()] = Balance(
                available=float(balance['available']),
                hold=float(balance['hold']))
        yield result

        # TODO: Add support for future balance changes.

    async def stream_candles(self, symbol, interval, start, end):
        current = floor_multiple(time_ms(), interval)

        if start < current:
            async for candle, primary in self._stream_historical_candles(symbol, interval, start,
                                                                         min(end, current)):
                yield candle, primary

        # TODO: Add support for future candles.

    async def _stream_historical_candles(self, symbol, interval, start, end):
        MAX_CANDLES_PER_REQUEST = 300  # They advertise 350.
        for page_start, page_end in page(start, end, interval, MAX_CANDLES_PER_REQUEST):
            url = (f'/products/{_product(symbol)}/candles'
                   f'?start={_datetime(page_start)}'
                   f'&end={_datetime(page_end)}'
                   f'&granularity={_granularity(interval)}')
            res = await self._public_request('GET', url)
            for c in reversed(res):
                # This seems to be an issue on Coinbase side. I didn't find any documentation for
                # this behavior but occasionally they send null values inside candle rows for
                # different price fields. Since we want to store all the data and we don't
                # currently use Coinbase for paper or live trading, we simply throw an exception.
                if None in c:
                    raise Exception(f'missing data for candle {c}; please re-run the command')
                yield (Candle(c[0] * 1000, float(c[3]), float(c[2]), float(c[1]), float(c[4]),
                       float(c[5])), True)

    async def stream_depth(self, symbol):
        async with self._session.ws_connect(_BASE_WS_URL) as ws:
            await ws.send_json({
                'type': 'subscribe',
                'product_ids': [_product(symbol)],
                'channels': ['level2']
            })
            async for msg in ws:
                data = json.loads(msg.data)
                if data['type'] == 'snapshot':
                    yield {
                        'type': 'snapshot',
                        'bids': [(float(p), float(s)) for p, s in data['bids']],
                        'asks': [(float(p), float(s)) for p, s in data['asks']]
                    }
                elif data['type'] == 'l2update':
                    bids = ((p, s) for side, p, s in data['changes'] if side == 'buy')
                    asks = ((p, s) for side, p, s in data['changes'] if side == 'sell')
                    yield {
                        'type': 'update',
                        'bids': [(float(p), float(s)) for p, s in bids],
                        'asks': [(float(p), float(s)) for p, s in asks]
                    }

    async def _public_request(self, method, url):
        await self._pub_limiter.acquire()
        url = _BASE_REST_URL + url
        async with self._session.request(method, url) as res:
            return await res.json()

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
            return await res.json()


def _product(symbol):
    return symbol.upper()


def _granularity(interval):
    return interval // 1000


def _datetime(timestamp):
    return datetime.utcfromtimestamp(timestamp / 1000.0).isoformat()
