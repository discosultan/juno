from decimal import Decimal
from typing import AsyncIterable

from juno.candles import Candle
from juno.candles.exchanges import Exchange
from juno.exchanges.coinbase import Session, to_interval, to_symbol, to_timestamp
from juno.itertools import page_limit


class Coinbase(Exchange):
    # Capabilities.
    can_stream_historical_candles: bool = True
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False

    def __init__(self, session: Session) -> None:
        self._session = session

    def map_candle_intervals(self) -> dict[int, int]:
        return {
            60000: 0,  # 1m
            300000: 0,  # 5m
            900000: 0,  # 15m
            3600000: 0,  # 1h
            21600000: 0,  # 6h
            86400000: 0,  # 1d
        }

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        MAX_CANDLES_PER_REQUEST = 300
        url = f'/products/{to_symbol(symbol)}/candles'
        for page_start, page_end in page_limit(start, end, interval, MAX_CANDLES_PER_REQUEST):
            _, content = await self._public_request(
                'GET', url, {
                    'start': to_timestamp(page_start),
                    'end': to_timestamp(page_end - 1),
                    'granularity': to_interval(interval)
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
