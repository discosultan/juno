from __future__ import annotations

import logging
from itertools import accumulate, chain
from typing import List

import plotly.graph_objs as go
import plotly.offline as py

from juno import Candle, Fill, indicators
from juno.components import Events
from juno.time import datetime_utcfromtimestamp_ms
from juno.trading import CloseReason, Position, TradingSummary

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Plotly(Plugin):
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
        close=[c.close for c in candles],
    ))
    # Volume.
    traces.append(go.Bar(
        x=times,
        y=[c.volume for c in candles],
        yaxis='y',
        marker={
            'color': ['#006400' if c.close >= c.open else '#8b0000' for c in candles]
        },
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
    # Profit.
    traces.append(trace_profit_pct_changes(summary))
    # traces.append(trace_balance(summary))
    # traces.append(trace_adx(candles))

    layout = {
        'yaxis': {
            'title': 'Volume',
            'domain': [0, 0.2],
        },
        'yaxis2': {
            'title': 'Price',
            'domain': [0.2, 0.8],
        },
        'yaxis3': {
            'title': 'Profit %',
            'domain': [0.8, 1.0],
        },
        'yaxis4': {
            'title': 'Balance',
            'side': 'right',
            'domain': [0.8, 1.0],
            'overlaying': 'y3',
        },
    }
    fig = go.Figure(data=traces, layout=layout)
    py.plot(fig)


def trace_position_openings(positions: List[Position.Closed], symbol: str) -> go.Scatter:
    return go.Scatter(
        mode='markers',
        x=[datetime_utcfromtimestamp_ms(p.open_time) for p in positions],
        y=[Fill.mean_price(p.open_fills) for p in positions],
        yaxis='y2',
        marker={
            'symbol': symbol,
            'color': 'green',
            'size': 16,
        },
    )


def trace_position_closings(positions: List[Position.Closed], color: str) -> go.Scatter:
    return go.Scatter(
        mode='markers',
        x=[datetime_utcfromtimestamp_ms(p.close_time) for p in positions],
        y=[Fill.mean_price(p.close_fills) for p in positions],
        yaxis='y2',
        marker={
            'color': color,
            'size': 8,
        },
    )


def trace_profit_pct_changes(summary: TradingSummary) -> go.Bar:
    positions = summary.list_positions()
    balances = list(accumulate(chain([summary.quote], (p.profit for p in positions))))
    profit_pct_changes = [100 * (b - a) / a for a, b in zip(balances[::1], balances[1::1])]
    return go.Bar(
        x=[datetime_utcfromtimestamp_ms(p.close_time) for p in positions],
        y=profit_pct_changes,
        yaxis='y3',
    )


def trace_balance(summary: TradingSummary) -> go.Scatter:
    positions = summary.list_positions()
    balances = list(accumulate(chain([summary.quote], (p.profit for p in positions))))
    times = list(
        map(
            datetime_utcfromtimestamp_ms,
            chain([summary.start], (p.close_time for p in positions))
        )
    )
    return go.Scatter(
        mode='lines',
        x=times,
        y=balances,
        yaxis='y4',
    )


def trace_adx(candles: List[Candle]) -> go.Scatter:
    adx = indicators.Adx(28)
    values = [adx.update(c.high, c.low) for c in candles]
    return go.Scatter(
        mode='lines',
        x=[datetime_utcfromtimestamp_ms(c.time) for c in candles],
        y=values,
        yaxis='y4',
    )
