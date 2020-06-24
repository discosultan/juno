from __future__ import annotations

import logging
from typing import List

import plotly.graph_objs as go
import plotly.offline as py

from juno import Candle, Fill
from juno.components import Events
from juno.time import datetime_utcfromtimestamp_ms
from juno.trading import CloseReason, Position, TradingSummary

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Discord(Plugin):
    def __init__(self, events: Events) -> None:
        self._events = events

    async def activate(self, agent_name: str, agent_type: str) -> None:
        candles = []

        @self._events.on(agent_name, 'candle')
        async def on_candle(candle: Candle) -> None:
            candles.append(candle)

        @self._events.on(agent_name, 'finished')
        async def on_finished(summary: TradingSummary) -> None:
            plot(candles, summary)

        _log.info(f'activated for {agent_name} ({agent_type})')


def plot(candles: List[Candle], summary: TradingSummary) -> None:
    times = [datetime_utcfromtimestamp_ms(c.time) for c in candles]

    traces = []
    # Candles.
    traces.append(go.Ohlc(
        x=times,
        yaxis='y2',
        open=[c.open for c in candles],
        high=[c.high for c in candles],
        low=[c.low for c in candles],
        close=[c.close for c in candles]
    ))
    # Volume.
    traces.append(go.Bar(
        x=times,
        y=[c.volume for c in candles],
        yaxis='y',
        marker={
            'color': ['#006400' if c.close >= c.open else '#8b0000' for c in candles]
        }
    ))
    # Openings.
    traces.extend([
        trace_position_openings(summary.list_positions(type_=Position.Long), 'triangle-up'),
        trace_position_openings(summary.list_positions(type_=Position.Short), 'triangle-down'),
    ])
    # Closings.
    traces.extend([
        trace_position_closings(summary.list_positions(reason=CloseReason.STRATEGY), 'yellow'),
        trace_position_closings(summary.list_positions(reason=CloseReason.TAKE_PROFIT), 'purple'),
        trace_position_closings(summary.list_positions(reason=CloseReason.STOP_LOSS), 'red'),
        trace_position_closings(summary.list_positions(reason=CloseReason.CANCELLED), 'gray'),
    ])

    layout = {
        'yaxis': {
            'domain': [0, 0.2],
        },
        'yaxis2': {
            'domain': [0.2, 0.8],
        },
    }
    fig = go.Figure(data=traces, layout=layout)
    py.plot(fig)


def trace_position_openings(positions: List[Position.Closed], symbol: str):
    return go.Scatter(
        x=[datetime_utcfromtimestamp_ms(p.open_time) for p in positions],
        y=[Fill.mean_price(p.open_fills) for p in positions],
        yaxis='y2',
        marker={
            'symbol': symbol,
            'color': 'green',
            'size': 16,
        },
        mode='markers',
    )


def trace_position_closings(positions: List[Position.Closed], color: str):
    return go.Scatter(
        x=[datetime_utcfromtimestamp_ms(p.close_time) for p in positions],
        y=[Fill.mean_price(p.close_fills) for p in positions],
        yaxis='y2',
        marker={
            'color': color,
            'size': 8,
        },
        mode='markers',
    )
