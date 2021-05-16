from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator

from juno.candles.models import Candle
from juno.exchanges.kraken import Kraken as Session
from juno.exchanges.kraken import to_ws_symbol
from juno.time import MIN_MS

from .exchange import Exchange


class Kraken(Exchange):
    can_stream_historical_candles: bool = False
    can_stream_historical_earliest_candle: bool = False
    can_stream_candles: bool = False

    def __init__(self, session: Session) -> None:
        self._session = session

    def map_candle_intervals(self) -> dict[int, int]:
        # TODO: Setup offsets.
        return {
            60000: 0,  # 1m
            300000: 0,  # 5m
            900000: 0,  # 15m
            1800000: 0,  # 30m
            3600000: 0,  # 1h
            14400000: 0,  # 4h
            86400000: 0,  # 1d
            604800000: 0,  # 1w
            1296000000: 0,  # 15d
        }

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        yield  # type: ignore

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        # https://docs.kraken.com/websockets/#message-ohlc
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

        async with self._session.public_ws.subscribe({
            'name': 'ohlc',
            'interval': interval // MIN_MS
        }, [to_ws_symbol(symbol)]) as ws:
            yield inner(ws)
