import asyncio
from typing import Union
from unittest.mock import MagicMock

from juno.asyncio import resolved_stream, stream_queue
from juno.candles import Candle, Chandler, Exchange


def mock_exchange_candles(
    can_stream_candles: bool = True,
    can_stream_historical_candles: bool = True,
    can_stream_historical_earliest_candle: bool = True,
    candle_intervals: dict[int, int] = {1: 0},
    historical_candles: list[Candle] = [],
    future_candles: Union[list[Candle], asyncio.Queue] = [],
) -> MagicMock:
    exchange = MagicMock(spec=Exchange)
    exchange.can_stream_candles = can_stream_candles
    exchange.can_stream_historical_candles = can_stream_historical_candles
    exchange.can_stream_historical_earliest_candle = can_stream_historical_earliest_candle
    exchange.map_candle_intervals.return_value = candle_intervals
    exchange.stream_historical_candles.return_value = resolved_stream(*historical_candles)
    exchange.connect_stream_candles.return_value.__aenter__.side_effect = lambda _: (
        stream_queue(future_candles, raise_on_exc=True)
        if isinstance(future_candles, asyncio.Queue)
        else resolved_stream(*future_candles)
    )
    return exchange


def mock_chandler() -> MagicMock:
    chandler = MagicMock(spec=Chandler)
    return chandler
