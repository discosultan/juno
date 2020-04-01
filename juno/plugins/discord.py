from __future__ import annotations

import asyncio
import logging
import weakref
from typing import Any, Dict

import discord

from juno.asyncio import cancel
from juno.components import Event
from juno.itertools import chunks
from juno.trading import LongPosition, OpenLongPosition, Position
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import exc_traceback, format_as_config

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Discord(discord.Client, Plugin):
    def __init__(self, event: Event, config: Dict[str, Any]) -> None:
        discord_config = config.get(type(self).__name__.lower(), {})
        # TODO: walrus
        token = discord_config.get('token')
        if not token:
            raise ValueError(f'Missing token from config')

        super().__init__()
        self._event = event
        self._token = token
        self._channel_ids = discord_config.get('channel_id', {})

    async def __aenter__(self) -> Discord:
        self._start_task = weakref.ref(asyncio.create_task(self.start(self._token)))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._start_task)
        await self.close()

    async def activate(self, agent_name: str, agent_type: str) -> None:
        channel_name = agent_type

        def format_message(
            title: str,
            content: Any,
            lang: str = 'json',
        ) -> str:
            return (
                f'{channel_name} agent {agent_name} {title}:\n```{lang}\n{content}\n```\n'
            )

        # TODO: walrus
        channel_id = self._channel_ids.get(channel_name)
        if not channel_id:
            raise ValueError(f'Missing {channel_name} channel ID from config')
        channel_id = int(channel_id)

        @self._event.on(agent_name, 'starting')
        async def on_starting(config: Any) -> None:
            await self._send_message(
                channel_id, format_message('starting with config', format_as_config(config))
            )

        @self._event.on(agent_name, 'position_opened')
        async def on_position_opened(pos: Position, result: Any) -> None:
            await self._send_message(
                channel_id,
                format_message(
                    f'opened {"long" if isinstance(pos, OpenLongPosition) else "short"} position',
                    format_as_config(pos),
                ),
            )

        @self._event.on(agent_name, 'position_closed')
        async def on_position_closed(pos: Position, result: Any) -> None:
            # We send separate messages to avoid exhausting max message length limit.
            await self._send_message(
                channel_id,
                format_message(
                    f'closed {"long" if isinstance(pos, LongPosition) else "short"} position',
                    format_as_config(pos),
                ),
            )
            await self._send_message(
                channel_id, format_message('summary', format_as_config(result))
            )

        @self._event.on(agent_name, 'finished')
        async def on_finished(result: Any) -> None:
            await self._send_message(
                channel_id, format_message('finished with summary', format_as_config(result))
            )

        @self._event.on(agent_name, 'errored')
        async def on_errored(exc: Exception) -> None:
            await self._send_message(
                channel_id, format_message('errored', exc_traceback(exc), lang='')
            )

        @self._event.on(agent_name, 'image')
        async def on_image(path: str):
            await self._send_file(channel_id, path)

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
