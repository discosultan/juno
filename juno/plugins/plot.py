from __future__ import annotations

import logging
from typing import Dict, Iterable

import plotly.graph_objs as go
import plotly.offline as py

from juno import Candle
from juno.components import Event
from juno.time import datetime_utcfromtimestamp_ms
from juno.trading import LongPosition, Position, ShortPosition, Trader

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Discord(Plugin):
    def __init__(self, event: Event) -> None:
        self._event = event

    async def activate(self, agent_name: str, agent_type: str) -> None:
        candles_map = {}

        @self._event.on(agent_name, 'candle')
        async def on_candle(candle: Candle) -> None:
            candles_map[candle.time] = candle

        @self._event.on(agent_name, 'finished')
        async def on_finished(result: Trader.State) -> None:
            assert result.summary
            plot(candles_map, result.summary.get_positions())

        _log.info(f'activated for {agent_name} ({agent_type})')


def plot(candles_map: Dict[int, Candle], positions: Iterable[Position]) -> None:
    candles = candles_map.values()
    times = [datetime_utcfromtimestamp_ms(c.time) for c in candles]

    trace1 = go.Ohlc(
        x=times,
        yaxis='y2',
        open=[c.open for c in candles],
        high=[c.high for c in candles],
        low=[c.low for c in candles],
        close=[c.close for c in candles]
    )
    long_positions = [p for p in positions if isinstance(p, LongPosition)]
    trace2 = go.Scatter(
        x=[datetime_utcfromtimestamp_ms(p.open_time) for p in long_positions],
        y=[candles_map[p.open_time].close for p in long_positions],
        yaxis='y2',
        marker={
            'color': 'green',
            'size': 12,
        },
        mode='markers',
    )
    short_positions = [p for p in positions if isinstance(p, ShortPosition)]
    trace3 = go.Scatter(
        x=[datetime_utcfromtimestamp_ms(p.open_time) for p in short_positions],
        y=[candles_map[p.open_time].close for p in short_positions],
        yaxis='y2',
        marker={
            'color': 'yellow',
            'size': 12,
        },
        mode='markers',
    )
    trace4 = go.Scatter(
        x=[datetime_utcfromtimestamp_ms(p.close_time) for p in positions],
        y=[candles_map[p.close_time].close for p in positions],
        yaxis='y2',
        marker={
            'color': 'red',
            'size': 12,
        },
        mode='markers',
    )
    trace5 = go.Bar(
        x=times,
        y=[c.volume for c in candles],
        yaxis='y',
        marker={
            'color': ['#006400' if c.close >= c.open else '#8b0000' for c in candles]
        }
    )
    data = [trace1, trace2, trace3, trace4, trace5]
    layout = {
        'yaxis': {
            'domain': [0, 0.2],
        },
        'yaxis2': {
            'domain': [0.2, 0.8],
        },
    }
    fig = go.Figure(data=data, layout=layout)
    py.plot(fig)
