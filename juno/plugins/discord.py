from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Dict, List

from discord import File
from discord.ext import commands
from more_itertools import sliced

from juno import Advice
from juno.asyncio import cancel, create_task_cancel_on_exc
from juno.components import Events
from juno.config import format_as_config
from juno.trading import Position, TradingSummary
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import exc_traceback, extract_public

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Discord(commands.Bot, Plugin):
    def __init__(self, events: Events, config: Dict[str, Any]) -> None:
        super().__init__(command_prefix='.')

        discord_config = config.get(type(self).__name__.lower(), {})
        if not (token := discord_config.get('token')):
            raise ValueError('Missing token from config')

        self._events = events
        self._token = token
        self._channel_ids = discord_config.get('channel_id', {})

    async def __aenter__(self) -> Discord:
        self._start_task = create_task_cancel_on_exc(self.start(self._token))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._start_task)
        await self.close()

    async def activate(self, agent_name: str, agent_type: str) -> None:
        channel_name = agent_type
        agent_state = None

        def format_message(
            title: str,
            content: Any,
            lang: str = '',
        ) -> str:
            return (
                f'{channel_name} agent {agent_name} {title}:\n```{lang}\n{content}\n```\n'
            )

        if not (channel_id := self._channel_ids.get(channel_name)):
            raise ValueError(f'Missing {channel_name} channel ID from config')
        channel_id = int(channel_id)
        send_message = partial(self._send_message, channel_id)
        send_file = partial(self._send_file, channel_id)

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

        @self.command(help='Make trader not open new positions')
        async def cordon(ctx: commands.Context) -> None:
            assert agent_state
            agent_state.result.open_new_positions = False
            msg = f'agent {agent_name} ({agent_type}) will no longer open new positions'
            _log.info(msg)
            await send_message(msg)

        @self.command(help='Make trader open new positions')
        async def uncordon(ctx: commands.Context) -> None:
            assert agent_state
            agent_state.result.open_new_positions = True
            msg = f'agent {agent_name} ({agent_type}) will open new positions'
            _log.info(msg)
            await send_message(msg)

        _log.info(f'activated for {agent_name} ({agent_type})')

        @self.command(help='Get trading summary if all open positions were closed right now')
        async def status(ctx: commands.Context) -> None:
            pass

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
