from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import plotly.graph_objs as go
import plotly.offline as py

from juno import Candle
from juno.components import Event
from juno.time import datetime_utcfromtimestamp_ms
from juno.trading import Trader

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
            positions = [(p.open_time, p.close_time) for p in result.summary.get_positions()]
            plot(candles_map, positions)

        _log.info(f'activated for {agent_name} ({agent_type})')


def plot(candles_map: Dict[int, Candle], positions: List[Tuple[int, int]]) -> None:
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
    trace2 = go.Scatter(
        x=[datetime_utcfromtimestamp_ms(a) for a, _ in positions],
        y=[candles_map[a].close for a, _ in positions],
        yaxis='y2',
        marker={
            'color': 'green',
            'size': 12,
        },
        mode='markers',
    )
    trace3 = go.Scatter(
        x=[datetime_utcfromtimestamp_ms(b) for _, b in positions],
        y=[candles_map[b].close for _, b in positions],
        yaxis='y2',
        marker={
            'color': 'red',
            'size': 12,
        },
        mode='markers',
    )
    trace4 = go.Bar(
        x=times,
        y=[c.volume for c in candles],
        yaxis='y',
        marker={
            'color': ['#006400' if c.close >= c.open else '#8b0000' for c in candles]
        }
    )
    data = [trace1, trace2, trace3, trace4]
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
