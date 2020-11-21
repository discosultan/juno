from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Dict, List

from discord import File
from discord.ext import commands
from more_itertools import sliced

from juno import Advice
from juno.asyncio import cancel, create_task_sigint_on_exception
from juno.components import Chandler, Events, Informant
from juno.config import format_as_config
from juno.time import MIN_MS, time_ms
from juno.trading import CloseReason, Position, SimulatedPositionMixin, TradingSummary
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import exc_traceback, extract_public

from .plugin import Plugin

_log = logging.getLogger(__name__)


# We use simulated position mixin to provide info for the `.status` command.
class Discord(commands.Bot, Plugin, SimulatedPositionMixin):
    def __init__(
        self, chandler: Chandler, informant: Informant, events: Events, config: Dict[str, Any]
    ) -> None:
        super().__init__(command_prefix='.')

        discord_config = config.get(type(self).__name__.lower(), {})
        if not (token := discord_config.get('token')):
            raise ValueError('Missing token from config')

        self._chandler = chandler
        self._informant = informant
        self._events = events
        self._token = token
        self._channel_ids = discord_config.get('channel_id', {})

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
        agent_state = None

        if not (channel_id := self._channel_ids.get(channel_name)):
            raise ValueError(f'Missing {channel_name} channel ID from config')

        channel_id = int(channel_id)
        send_message = partial(self._send_message, channel_id)
        send_file = partial(self._send_file, channel_id)
        format_message = partial(self._format_message, channel_name, agent_name)

        @self._events.on(agent_name, 'starting')
        async def on_starting(config: Any, state: Any) -> None:
            nonlocal agent_state
            agent_state = state
            await send_message(
                format_message('starting with config', format_as_config(config), lang='json')
            )

        @self._events.on(agent_name, 'positions_opened')
        async def on_positions_opened(positions: List[Position], summary: TradingSummary) -> None:
            await asyncio.gather(
                *(send_message(
                    format_message(
                        f'opened {"long" if isinstance(p, Position.OpenLong) else "short"} '
                        'position',
                        format_as_config(extract_public(p, exclude=['fills'])),
                        lang='json',
                    ),
                ) for p in positions)
            )

        @self._events.on(agent_name, 'positions_closed')
        async def on_positions_closed(positions: List[Position], summary: TradingSummary) -> None:
            # We send separate messages to avoid exhausting max message length limit.
            await asyncio.gather(
                *(send_message(
                    format_message(
                        f'closed {"long" if isinstance(p, Position.Long) else "short"} '
                        'position',
                        format_as_config(
                            extract_public(p, exclude=['open_fills', 'close_fills'])
                        ),
                        lang='json',
                    ),
                ) for p in positions)
            )
            await send_message(
                format_message('summary', format_as_config(extract_public(summary)), lang='json')
            )

        @self._events.on(agent_name, 'finished')
        async def on_finished(summary: TradingSummary) -> None:
            await send_message(
                format_message(
                    'finished with summary',
                    format_as_config(extract_public(summary)),
                    lang='json',
                ),
            )

        @self._events.on(agent_name, 'errored')
        async def on_errored(exc: Exception) -> None:
            await send_message(format_message('errored', exc_traceback(exc)))

        @self._events.on(agent_name, 'image')
        async def on_image(path: str) -> None:
            await send_file(path)

        @self._events.on(agent_name, 'advice')
        async def on_advice(advice: Advice) -> None:
            await send_message(format_message('received advice', advice.name))

        @self.command(help='Set whether trader closes positions on exit')
        async def close_on_exit(ctx: commands.Context, value: str):
            if ctx.channel.name != channel_name:
                return
            if value not in ['true', 'false']:
                await send_message(
                    'please pass true/false to set whether trader will close positions on exit'
                )
                return
            assert agent_state

            close_on_exit = True if value == 'true' else False
            agent_state.result.close_on_exit = close_on_exit
            msg = (
                f'agent {agent_name} ({agent_type}) will{"" if close_on_exit else " not"} close '
                'positions on exit'
            )
            _log.info(msg)
            await send_message(msg)

        @self.command(help='Set whether trader opens new positions')
        async def open_new_positions(ctx: commands.Context, value: str) -> None:
            if ctx.channel.name != channel_name:
                return
            if value not in ['true', 'false']:
                await send_message(
                    'please pass true/false to set whether trader will open new positions'
                )
                return
            assert agent_state

            open_new_positions = True if value == 'true' else False
            agent_state.result.open_new_positions = open_new_positions
            msg = (
                f'agent {agent_name} ({agent_type}) will{"" if open_new_positions else " not"} '
                'open new positions'
            )
            _log.info(msg)
            await send_message(msg)

        @self.command(help='Get trading summary if all open positions were closed right now')
        async def status(ctx: commands.Context) -> None:
            if ctx.channel.name != channel_name:
                return

            assert agent_state
            trader_state = agent_state.result
            trader_state.summary
            await send_message(
                format_message(
                    'summary',
                    format_as_config(extract_public(trader_state.summary)),
                    lang='json',
                )
            )
            await asyncio.gather(*(
                self._send_open_position_status(ctx.channel.id, agent_type, agent_name, p)
                for p in trader_state.open_positions
            ))

        _log.info(f'activated for {agent_name} ({agent_type})')

    async def _send_open_position_status(
        self, channel_id: int, agent_type: str, agent_name: str, pos: Position.Open
    ) -> None:
        last_candle = await self._chandler.get_last_candle(pos.exchange, pos.symbol, MIN_MS)
        closed_pos: Position.Closed
        if isinstance(pos, Position.OpenLong):
            closed_pos = self.close_simulated_long_position(
                pos, time_ms(), last_candle.close, CloseReason.CANCELLED
            )
        else:
            closed_pos = self.close_simulated_short_position(
                pos, time_ms(), last_candle.close, CloseReason.CANCELLED
            )
        await self._send_message(
            channel_id,
            self._format_message(
                agent_type,
                agent_name,
                f'{"long" if isinstance(pos, Position.OpenLong) else "short"} position open; if '
                'closed now',
                format_as_config(
                    extract_public(closed_pos, exclude=['open_fills', 'close_fills'])
                ),
                lang='json',
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
        self,
        channel_name: str,
        agent_name: str,
        title: str,
        content: Any,
        lang: str = '',
    ) -> str:
        return (
            f'{channel_name} agent {agent_name} {title}:\n```{lang}\n{content}\n```\n'
        )
