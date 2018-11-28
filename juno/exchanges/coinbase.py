from datetime import datetime

from juno.http import ClientSession
from juno.math import floor_multiple
from juno.time import time_ms
from juno.utils import LeakyBucket, page


class Coinbase:

    def __init__(self, api_key: str, secret_key: str):
        self._session = None
        self._api_key = api_key
        self._secret_key = secret_key

        self.default_fees = Fees(0.0, 0.0025)
        self.name = self.__class__.__name__

        # Rate limiter.
        self._pub_limiter = LeakyBucket(rate=1, period=1)   # They advertise 3 per sec.
        self._priv_limiter = LeakyBucket(rate=5, period=1)  # They advertise 5 per sec.

    async def __aenter__(self):
        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_symbol_info(self, symbol):
        res = await self._public_request('https://api.pro.coinbase.com/products')
        product = (x for x in res if x['id'] == _product(symbol)).__next__()

        return AssetPairInfo(
            time_ms(),
            symbol,
            1_000_000_000,
            1_000_000_000,
            float(product['quote_increment']),
            1_000_000_000.0,
            float(product['quote_increment']),
            float(product['base_min_size']),
            float(product['base_max_size']),
            float(product['base_min_size']))

    async def get_account_info(self):
        return AccountInfo(time_ms(), 100.0, 0.0, self.default_fees)

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
            url = (f'https://api.pro.coinbase.com/products/{_product(symbol)}/candles'
                   f'?start={_datetime(page_start)}'
                   f'&end={_datetime(page_end)}'
                   f'&granularity={_granularity(interval)}')
            res = await self._public_request(url)
            for c in reversed(res):
                # This seems to be an issue on Coinbase side. I didn't find any documentation for
                # this behavior but occasionally they send null values inside candle rows for
                # different price fields. Since we want to store all the data and we don't
                # currently use Coinbase for paper or live trading, we simply throw an exception.
                if None in c:
                    raise Exception(f'missing data for candle {c}; please re-run the command')
                yield (Candle(c[0] * 1000, float(c[3]), float(c[2]), float(c[1]), float(c[4]),
                       float(c[5])), True)

    async def _public_request(self, url):
        await self._pub_limiter.acquire()
        async with self._session.get(url) as res:
            return await res.json()


def _product(symbol):
    return symbol.upper()


def _granularity(interval):
    return interval // 1000


def _datetime(timestamp):
    return datetime.utcfromtimestamp(timestamp / 1000.0).isoformat()
