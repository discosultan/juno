from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Optional

from more_itertools import sliced
from nextcord import File
from nextcord.ext.commands.bot import Bot, Context

from juno import json, serialization
from juno.asyncio import cancel, create_task_sigint_on_exception
from juno.components import Chandler, Events, Informant
from juno.positioner import SimulatedPositioner
from juno.time import MIN_MS, time_ms
from juno.traders import Trader
from juno.trading import CloseReason, Position, TradingSummary
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import exc_traceback, extract_public

from .plugin import Plugin

_log = logging.getLogger(__name__)


class _TraderContext:
    def __init__(self, state: Any, instance: Trader) -> None:
        self.state = state
        self.instance = instance


# We use simulated position mixin to provide info for the `.status` command.
class Discord(Bot, Plugin):
    def __init__(
        self, chandler: Chandler, informant: Informant, events: Events, config: dict[str, Any]
    ) -> None:
        super().__init__(command_prefix=".")

        discord_config = config.get(type(self).__name__.lower(), {})

        if not (token := discord_config.get("token")):
            raise ValueError("Missing token from config")
        if not isinstance(token, str):
            raise ValueError("Token should be a string")

        channel_ids = discord_config.get("channel_id", {})
        if not isinstance(channel_ids, dict):
            raise ValueError(
                f"Channel IDs should be a map but was a {type(channel_ids).__name__} instead"
            )

        self._chandler = chandler
        self._informant = informant
        self._events = events
        self._token = token
        self._channel_ids = channel_ids
        self._simulated_positioner = SimulatedPositioner(informant=informant)

    async def __aenter__(self) -> Discord:
        self._start_task = create_task_sigint_on_exception(self.start(self._token))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._start_task)
        await self.close()

    @property
    def informant(self) -> Informant:
        return self._informant

    async def activate(self, agent_name: str, agent_type: str) -> None:
        channel_name = agent_type
        trader_ctx: Optional[_TraderContext] = None

        if not (channel_id := self._channel_ids.get(channel_name)):
            raise ValueError(f"Missing {channel_name} channel ID from config")

        channel_id = int(channel_id)
        send_message = partial(self._send_message, channel_id)
        send_file = partial(self._send_file, channel_id)
        format_message = partial(_format_message, channel_name, agent_name)

        @self._events.on(agent_name, "starting")
        async def on_starting(config: Any, state: Any, trader: Trader) -> None:
            nonlocal trader_ctx
            trader_ctx = _TraderContext(
                state=state.result,
                instance=trader,
            )
            await send_message(
                format_message(
                    "starting with config",
                    json.dumps(serialization.config.serialize(config), indent=4),
                    lang="json",
                )
            )

        @self._events.on(agent_name, "positions_opened")
        async def on_positions_opened(positions: list[Position], summary: TradingSummary) -> None:
            await asyncio.gather(
                *(
                    send_message(
                        format_message(
                            f'opened {"long" if isinstance(p, Position.OpenLong) else "short"} '
                            "position",
                            json.dumps(
                                serialization.config.serialize(
                                    extract_public(p, exclude=["fills"])
                                ),
                                indent=4,
                            ),
                            lang="json",
                        ),
                    )
                    for p in positions
                )
            )

        @self._events.on(agent_name, "positions_closed")
        async def on_positions_closed(positions: list[Position], summary: TradingSummary) -> None:
            # We send separate messages to avoid exhausting max message length limit.
            await asyncio.gather(
                *(
                    send_message(
                        format_message(
                            f'closed {"long" if isinstance(p, Position.Long) else "short"} '
                            "position",
                            json.dumps(
                                serialization.config.serialize(
                                    extract_public(p, exclude=["open_fills", "close_fills"])
                                ),
                                indent=4,
                            ),
                            lang="json",
                        ),
                    )
                    for p in positions
                )
            )
            await send_message(
                format_message(
                    "summary",
                    json.dumps(serialization.config.serialize(extract_public(summary)), indent=4),
                    lang="json",
                )
            )

        @self._events.on(agent_name, "finished")
        async def on_finished(summary: TradingSummary) -> None:
            await send_message(
                format_message(
                    "finished with summary",
                    json.dumps(serialization.config.serialize(extract_public(summary)), indent=4),
                    lang="json",
                ),
            )

        @self._events.on(agent_name, "errored")
        async def on_errored(exc: Exception) -> None:
            await send_message(format_message("errored", exc_traceback(exc)))

        @self._events.on(agent_name, "image")
        async def on_image(path: str) -> None:
            await send_file(path)

        @self._events.on(agent_name, "message")
        async def on_message(message: str) -> None:
            await send_message(format_message("received message", message))

        async def open_positions(ctx: Context, value: str, short: bool) -> None:
            if ctx.channel.name != channel_name:
                return
            assert trader_ctx

            symbols = value.split(",")

            await send_message(f"opening {symbols} {'short' if short else 'long'} positions")
            try:
                await trader_ctx.instance.open_positions(
                    state=trader_ctx.state,
                    symbols=symbols,
                    short=short,
                )
            except ValueError as e:
                await send_message(f"could not open positions for {symbols}: {e}")
            except Exception:
                msg = "unhandled exception while opening positions"
                _log.exception(msg)
                await send_message(msg)
                raise

        @self.command(help="Opens new long positions by specified comma-separated symbols")
        async def open_long_positions(ctx: Context, value: str) -> None:
            await open_positions(ctx, value, False)

        @self.command(help="Opens new short positions by specified comma-separated symbols")
        async def open_short_positions(ctx: Context, value: str) -> None:
            await open_positions(ctx, value, True)

        @self.command(help="Closes open positions by specified comma-separated symbols")
        async def close_positions(ctx: Context, value: str) -> None:
            if ctx.channel.name != channel_name:
                return
            assert trader_ctx

            symbols = value.split(",")

            await send_message(f"closing {symbols} positions")
            try:
                await trader_ctx.instance.close_positions(
                    state=trader_ctx.state,
                    symbols=symbols,
                    reason=CloseReason.CANCELLED,
                )
            except ValueError as e:
                await send_message(f"could not close positions for {symbols}: {e}")
            except Exception:
                msg = "unhandled exception while closing positions"
                _log.exception(msg)
                await send_message(msg)
                raise

        @self.command(help="Sets whether trader closes positions on exit")
        async def close_on_exit(ctx: Context, value: str) -> None:
            if ctx.channel.name != channel_name:
                return
            if value not in ["true", "false"]:
                await send_message(
                    "please pass true/false to set whether trader will close positions on exit"
                )
                return
            assert trader_ctx

            close_on_exit = True if value == "true" else False
            trader_ctx.state.close_on_exit = close_on_exit
            msg = (
                f'agent {agent_name} ({agent_type}) will{"" if close_on_exit else " not"} close '
                "positions on exit"
            )
            _log.info(msg)
            await send_message(msg)

        @self.command(help="Sets whether trader opens new positions")
        async def open_new_positions(ctx: Context, value: str) -> None:
            if ctx.channel.name != channel_name:
                return
            if value not in ["true", "false"]:
                await send_message(
                    "please pass true/false to set whether trader will open new positions"
                )
                return
            assert trader_ctx

            open_new_positions = True if value == "true" else False
            trader_ctx.state.open_new_positions = open_new_positions
            msg = (
                f'agent {agent_name} ({agent_type}) will{"" if open_new_positions else " not"} '
                "open new positions"
            )
            _log.info(msg)
            await send_message(msg)

        @self.command(help="Gets trading summary if all open positions were closed right now")
        async def status(ctx: Context) -> None:
            if ctx.channel.name != channel_name:
                return
            assert trader_ctx

            await send_message(
                format_message(
                    "summary",
                    json.dumps(
                        serialization.config.serialize(extract_public(trader_ctx.state.summary)),
                        indent=4,
                    ),
                    lang="json",
                )
            )
            await asyncio.gather(
                *(
                    self._send_open_position_status(ctx.channel.id, agent_type, agent_name, p)
                    for p in trader_ctx.state.open_positions
                )
            )

        _log.info(f"activated for {agent_name} ({agent_type})")

    async def _send_open_position_status(
        self, channel_id: int, agent_type: str, agent_name: str, pos: Position.Open
    ) -> None:
        last_candle = await self._chandler.get_last_candle(pos.exchange, pos.symbol, MIN_MS)
        closed_pos: Position.Closed
        (closed_pos,) = self._simulated_positioner.close_simulated_positions(
            [(pos, CloseReason.CANCELLED, time_ms(), last_candle.close)]
        )
        await self._send_message(
            channel_id,
            _format_message(
                agent_type,
                agent_name,
                f'{"long" if isinstance(pos, Position.OpenLong) else "short"} position open; if '
                "closed now",
                json.dumps(
                    serialization.config.serialize(
                        extract_public(closed_pos, exclude=["open_fills", "close_fills"])
                    ),
                    indent=4,
                ),
                lang="json",
            ),
        )

    async def _send_message(self, channel_id: int, msg: str) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(channel_id)
        max_length = 2000
        # We break the message and send it in chunks in case it exceeds the max allowed limit.
        # Note that this is bad as it will break formatting. Splitting is done by chars and not
        # words.
        for msg_slice in sliced(msg, max_length):
            await channel.send(msg_slice)

    async def _send_file(self, channel_id: int, path: str) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(channel_id)
        await channel.send(file=File(path))


def _format_message(
    channel_name: str,
    agent_name: str,
    title: str,
    content: Any,
    lang: str = "",
) -> str:
    return f"{channel_name} agent {agent_name} {title}:\n```{lang}\n{content}\n```\n"
