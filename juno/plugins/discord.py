from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import discord

from juno import Advice
from juno.asyncio import cancel, create_task_cancel_on_exc
from juno.components import Events
from juno.config import format_as_config
from juno.itertools import chunks
from juno.trading import Position, TradingSummary
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import exc_traceback, extract_public

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Discord(discord.Client, Plugin):
    def __init__(self, events: Events, config: Dict[str, Any]) -> None:
        discord_config = config.get(type(self).__name__.lower(), {})
        if not (token := discord_config.get('token')):
            raise ValueError('Missing token from config')

        super().__init__()
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

        @self._events.on(agent_name, 'starting')
        async def on_starting(config: Any) -> None:
            await self._send_message(
                channel_id,
                format_message('starting with config', format_as_config(config), lang='json')
            )

        @self._events.on(agent_name, 'positions_opened')
        async def on_positions_opened(positions: List[Position], summary: TradingSummary) -> None:
            await asyncio.gather(
                *(self._send_message(
                    channel_id,
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
                *(self._send_message(
                    channel_id,
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
            await self._send_message(
                channel_id,
                format_message('summary', format_as_config(extract_public(summary)), lang='json')
            )

        @self._events.on(agent_name, 'finished')
        async def on_finished(summary: TradingSummary) -> None:
            await self._send_message(
                channel_id,
                format_message(
                    'finished with summary',
                    format_as_config(extract_public(summary)),
                    lang='json',
                ),
            )

        @self._events.on(agent_name, 'errored')
        async def on_errored(exc: Exception) -> None:
            await self._send_message(
                channel_id, format_message('errored', exc_traceback(exc))
            )

        @self._events.on(agent_name, 'image')
        async def on_image(path: str) -> None:
            await self._send_file(channel_id, path)

        @self._events.on(agent_name, 'advice')
        async def on_advice(advice: Advice) -> None:
            await self._send_message(
                channel_id, format_message('received advice', advice.name)
            )

        _log.info(f'activated for {agent_name} ({agent_type})')

    async def _send_message(self, channel_id: int, msg: str) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(channel_id)
        max_length = 2000
        # We break the message and send it in chunks in case it exceeds the max allowed limit.
        # Note that this is bad as it will break formatting. Splitting is done by chars and not
        # words.
        for chunk in chunks(msg, max_length):
            await channel.send(chunk)

    async def _send_file(self, channel_id: int, path: str) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(channel_id)
        await channel.send(file=discord.File(path))
