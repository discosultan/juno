from __future__ import annotations

import logging

from juno import Interval_
from juno.components import Events
from juno.path import save_text_file
from juno.trading import Position, TradingSummary

from .plugin import Plugin

_log = logging.getLogger(__name__)


class PineScript(Plugin):
    def __init__(self, events: Events) -> None:
        self._events = events

    async def activate(self, agent_name: str, agent_type: str) -> None:
        @self._events.on(agent_name, "finished")
        async def on_finished(summary: TradingSummary) -> None:
            save_text_file(get_script(summary), "strategy.pine")

        _log.info(f"activated for {agent_name} ({agent_type})")


def get_script(summary: TradingSummary) -> str:
    longs = [p for p in summary.positions if isinstance(p, Position.Long)]
    shorts = [p for p in summary.positions if isinstance(p, Position.Short)]
    pos: Position.Closed

    lines = [
        (
            "// This source code is subject to the terms of the Mozilla Public License 2.0 at "
            "https://mozilla.org/MPL/2.0/"
        ),
        "// © discosultan",
        "",
        "//@version=5",
        'indicator("juno", overlay=true)',
        "",
    ]

    # Open longs.
    lines.append(f"var open_longs = array.new_int({len(longs)})")
    for i, pos in enumerate(longs):
        time = adjust_time(pos.open_time)
        lines.append(f"array.set(open_longs, {i}, {time})")
    lines.append("open_longs_data = array.includes(open_longs, time)")
    lines.append(
        "plotshape(open_longs_data, style=shape.triangleup, location=location.belowbar, "
        "color=color.green)"
    )

    # Close longs.
    lines.append(f"var close_longs = array.new_int({len(longs)})")
    for i, pos in enumerate(longs):
        time = adjust_time(pos.close_time)
        lines.append(f"array.set(close_longs, {i}, {time})")
        lines.append(
            f'label.new({time}, high, text="{pos.profit}", xloc=xloc.bar_time, '
            "yloc=yloc.abovebar,  style=label.style_label_down)"
        )
    lines.append("close_longs_data = array.includes(close_longs, time)")
    lines.append(
        "plotshape(close_longs_data, style=shape.xcross, location=location.abovebar, "
        "color=color.green)"
    )

    # Open shorts.
    lines.append(f"var open_shorts = array.new_int({len(shorts)})")
    for i, pos in enumerate(shorts):
        time = adjust_time(pos.open_time)
        lines.append(f"array.set(open_shorts, {i}, {time})")
    lines.append("open_shorts_data = array.includes(open_shorts, time)")
    lines.append(
        "plotshape(open_shorts_data, style=shape.triangledown, location=location.abovebar, "
        "color=color.red)"
    )

    # Close shorts.
    lines.append(f"var close_shorts = array.new_int({len(shorts)})")
    for i, pos in enumerate(shorts):
        time = adjust_time(pos.close_time)
        lines.append(f"array.set(close_shorts, {i}, {time})")
        lines.append(
            f'label.new({time}, low, text="{pos.profit}", xloc=xloc.bar_time, '
            "yloc=yloc.belowbar, style=label.style_label_up)"
        )
    lines.append("close_shorts_data = array.includes(close_shorts, time)")
    lines.append(
        "plotshape(close_shorts_data, style=shape.xcross, location=location.belowbar, "
        "color=color.red)"
    )

    return "\n".join(lines)


def adjust_time(time: int) -> int:
    # TODO: This interval hardcoded for a specific strategy. This is to plot the markers on the
    # closing candles and not on the opening ones.
    return time - Interval_.MIN
