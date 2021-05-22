import asyncio
from typing import Union
from unittest.mock import MagicMock

from juno.asyncio import resolved_stream, stream_queue
from juno.trades import Exchange, Trade, Trades


def mock_exchange_trades(
    historical_trades: list[Trade] = [],
    future_trades: Union[list[Trade], asyncio.Queue] = [],
) -> MagicMock:
    exchange = MagicMock(spec=Exchange)
    exchange.stream_historical_trades.return_value = resolved_stream(*historical_trades)
    exchange.connect_stream_trades.return_value.__aenter__.side_effect = lambda: (
        stream_queue(future_trades, raise_on_exc=True)
        if isinstance(future_trades, asyncio.Queue)
        else resolved_stream(*future_trades)
    )
    return exchange


def mock_trades(trades: list[Trade]) -> MagicMock:
    trades = MagicMock(spec=Trades)
    trades.stream_trades.return_value = resolved_stream(*trades)
    return trades
