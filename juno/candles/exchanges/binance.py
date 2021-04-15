from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator

from juno.candles import Candle
from juno.candles.exchanges import Exchange
from juno.exchanges.binance import Session, to_http_symbol, to_ws_symbol
from juno.itertools import page
from juno.time import HOUR_SEC, strfinterval


class Binance(Exchange):
    # Capabilities.
    can_stream_historical_candles: bool = True
    can_stream_historical_earliest_candle: bool = True
    can_stream_candles: bool = True

    def __init__(self, session: Session) -> None:
        self._session = session

    def map_candle_intervals(self) -> dict[int, int]:
        return {
            60000: 0,  # 1m
            180000: 0,  # 3m
            300000: 0,  # 5m
            900000: 0,  # 15m
            1800000: 0,  # 30m
            3600000: 0,  # 1h
            7200000: 0,  # 2h
            14400000: 0,  # 4h
            21600000: 0,  # 6h
            28800000: 0,  # 8h
            43200000: 0,  # 12h
            86400000: 0,  # 1d
            259200000: 0,  # 3d
            604800000: 345600000,  # 1w 4d
            2629746000: 2541726000,  # 1M 4w1d10h2m6s
        }

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        limit = 1000  # Max possible candles per request.
        binance_interval = strfinterval(interval)
        binance_symbol = to_http_symbol(symbol)
        # Start 0 is a special value indicating that we try to find the earliest available candle.
        pagination_interval = interval
        if start == 0:
            pagination_interval = end - start
        for page_start, page_end in page(start, end, pagination_interval, limit):
            content = await self._session.request_json(
                method='GET',
                url='/api/v3/klines',
                weight=1,
                data={
                    'symbol': binance_symbol,
                    'interval': binance_interval,
                    'startTime': page_start,
                    'endTime': page_end - 1,
                    'limit': limit,
                }
            )
            for c in content:
                # Binance can return bad candles where the time does not fall within the requested
                # interval. For example, the second candle of the following query has bad time:
                # https://api.binance.com/api/v1/klines?symbol=ETHBTC&interval=4h&limit=10&startTime=1529971200000&endTime=1530000000000
                yield Candle(
                    c[0], Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]),
                    Decimal(c[5]), True
                )

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        # Binance disconnects a websocket connection every 24h. Therefore, we reconnect every 12h.
        # Note that two streams will send events with matching evt_times.
        # This can be used to switch from one stream to another and avoiding the edge case where
        # we miss out on the very last update to a candle.

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Candle]:
            async for data in ws:
                c = data['k']
                yield Candle(
                    c['t'], Decimal(c['o']), Decimal(c['h']), Decimal(c['l']), Decimal(c['c']),
                    Decimal(c['v']), c['x']
                )

        async with self._session.connect_refreshing_stream(
            url=f'/ws/{to_ws_symbol(symbol)}@kline_{strfinterval(interval)}',
            interval=12 * HOUR_SEC,
            name='candles',
            raise_on_disconnect=True
        ) as ws:
            yield inner(ws)
