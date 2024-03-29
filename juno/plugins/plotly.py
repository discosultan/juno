from __future__ import annotations

import logging
from itertools import accumulate, chain

import plotly.graph_objs as go
import plotly.offline as py

from juno import Candle, Fill, Symbol, Timestamp_, indicators
from juno.components import Events
from juno.trading import CloseReason, Position, TradingSummary

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Plotly(Plugin):
    def __init__(self, events: Events) -> None:
        self._events = events

    async def activate(self, agent_name: str, agent_type: str) -> None:
        candles = []

        @self._events.on(agent_name, "candle")
        async def on_candle(candle: Candle) -> None:
            candles.append(candle)

        @self._events.on(agent_name, "finished")
        async def on_finished(summary: TradingSummary) -> None:
            plot(candles, summary)

        _log.info(f"activated for {agent_name} ({agent_type})")


def plot(candles: list[Candle], summary: TradingSummary) -> None:
    times = [Timestamp_.to_datetime_utc(c.time) for c in candles]

    traces = []
    # Candles.
    traces.append(
        go.Ohlc(
            x=times,
            yaxis="y2",
            open=[c.open for c in candles],
            high=[c.high for c in candles],
            low=[c.low for c in candles],
            close=[c.close for c in candles],
        )
    )
    # Volume.
    traces.append(
        go.Bar(
            x=times,
            y=[c.volume for c in candles],
            yaxis="y",
            marker={"color": ["#006400" if c.close >= c.open else "#8b0000" for c in candles]},
        )
    )
    # Openings.
    traces.extend(
        [
            trace_position_openings(
                [p for p in summary.positions if isinstance(p, Position.Long)], "triangle-up"
            ),
            trace_position_openings(
                [p for p in summary.positions if isinstance(p, Position.Short)], "triangle-down"
            ),
        ]
    )
    # Closings.
    traces.extend(
        [
            trace_position_closings(
                [p for p in summary.positions if p.close_reason == CloseReason.STRATEGY], "yellow"
            ),
            trace_position_closings(
                [p for p in summary.positions if p.close_reason == CloseReason.TAKE_PROFIT],
                "purple",
            ),
            trace_position_closings(
                [p for p in summary.positions if p.close_reason == CloseReason.STOP_LOSS], "red"
            ),
            trace_position_closings(
                [p for p in summary.positions if p.close_reason == CloseReason.CANCELLED], "gray"
            ),
        ]
    )
    # Profit.
    traces.append(trace_profit_pct_changes(summary))
    # traces.append(trace_balance(summary))
    # traces.append(trace_adx(candles))

    layout = {
        "yaxis": {
            "title": "Volume",
            "domain": [0, 0.2],
        },
        "yaxis2": {
            "title": "Price",
            "domain": [0.2, 0.8],
        },
        "yaxis3": {
            "title": "Profit %",
            "domain": [0.8, 1.0],
        },
        "yaxis4": {
            "title": "Balance",
            "side": "right",
            "domain": [0.8, 1.0],
            "overlaying": "y3",
        },
    }
    fig = go.Figure(data=traces, layout=layout)
    py.plot(fig)


def trace_position_openings(positions: list[Position.Closed], symbol: Symbol) -> go.Scatter:
    return go.Scatter(
        mode="markers",
        x=[Timestamp_.to_datetime_utc(p.open_time) for p in positions],
        y=[Fill.mean_price(p.open_fills) for p in positions],
        yaxis="y2",
        marker={
            "symbol": symbol,
            "color": "green",
            "size": 16,
        },
    )


def trace_position_closings(positions: list[Position.Closed], color: str) -> go.Scatter:
    return go.Scatter(
        mode="markers",
        x=[Timestamp_.to_datetime_utc(p.close_time) for p in positions],
        y=[Fill.mean_price(p.close_fills) for p in positions],
        yaxis="y2",
        marker={
            "color": color,
            "size": 8,
        },
    )


def trace_profit_pct_changes(summary: TradingSummary) -> go.Bar:
    positions = summary.positions
    # TODO: assumes only single starting asset. we should use a benchmark asset similar to
    # extended statistics instead.
    quote = list(summary.starting_assets.values())[0]
    balances = list(accumulate(chain([quote], (p.profit for p in positions))))
    profit_pct_changes = [100 * (b - a) / a for a, b in zip(balances[::1], balances[1::1])]
    return go.Bar(
        x=[Timestamp_.to_datetime_utc(p.close_time) for p in positions],
        y=profit_pct_changes,
        yaxis="y3",
    )


def trace_balance(summary: TradingSummary) -> go.Scatter:
    positions = summary.positions
    # TODO: assumes only single starting asset. we should use a benchmark asset similar to
    # extended statistics instead.
    quote = list(summary.starting_assets.values())[0]
    balances = list(accumulate(chain([quote], (p.profit for p in positions))))
    times = list(
        map(Timestamp_.to_datetime_utc, chain([summary.start], (p.close_time for p in positions)))
    )
    return go.Scatter(
        mode="lines",
        x=times,
        y=balances,
        yaxis="y4",
    )


def trace_adx(candles: list[Candle]) -> go.Scatter:
    adx = indicators.Adx(28)
    values = [adx.update(c.high, c.low) for c in candles]
    return go.Scatter(
        mode="lines",
        x=[Timestamp_.to_datetime_utc(c.time) for c in candles],
        y=values,
        yaxis="y4",
    )
