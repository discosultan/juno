from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import discord

from juno.agents import Agent
from juno.asyncio import cancel, cancelable
from juno.itertools import chunks
from juno.trading import Position
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import exc_traceback, format_as_config

_log = logging.getLogger(__name__)


@asynccontextmanager
async def activate(agent: Agent, plugin_config: Dict[str, Any]) -> AsyncIterator[None]:
    def format_message(title: str, content: Any, lang: str = 'json') -> str:
        return f'{type(agent).__name__} agent {agent.name} {title}:\n```{lang}\n{content}\n```\n'

    token = plugin_config.get('token')
    if not token:
        raise ValueError('Missing Discord token from config')

    channel_name = type(agent).__name__.lower()
    channel_id = plugin_config.get('channel_id', {}).get(channel_name)
    if not channel_id:
        raise ValueError(f'Missing {channel_name} channel ID from config')

    async with Discord(token=token, channel_id=channel_id) as client:
        @agent.on('starting')
        async def on_starting() -> None:
            await client.send_message(
                format_message('starting with config', agent.config)
            )

        @agent.on('position_opened')
        async def on_position_opened(pos: Position) -> None:
            # We send separate messages to avoid exhausting max message length limit.
            await client.send_message(format_message('opened position', format_as_config(pos)))
            await client.send_message(
                format_message('summary', format_as_config((agent.result)))
            )

        @agent.on('position_closed')
        async def on_position_closed(pos: Position) -> None:
            await client.send_message(format_message('closed position', format_as_config(pos)))
            await client.send_message(
                format_message('summary', format_as_config(agent.result))
            )

        @agent.on('finished')
        async def on_finished() -> None:
            await client.send_message(
                format_message('finished with summary', format_as_config(agent.result))
            )

        @agent.on('errored')
        async def on_errored(exc: Exception) -> None:
            await client.send_message(format_message('errored', exc_traceback(exc), lang=''))
            await client.send_message(
                format_message('summary', format_as_config(agent.result))
            )

        @agent.on('image')
        async def on_image(path: str):
            await client.send_file(path)

        _log.info('activated')
        yield


class Discord(discord.Client):
    def __init__(self, token: str, channel_id: str) -> None:
        super().__init__()
        self._token = token
        self._channel_id = int(channel_id)

    async def __aenter__(self) -> Discord:
        self._start_task = asyncio.create_task(cancelable(self.start(self._token)))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await cancel(self._start_task)
        await self.close()

    async def send_message(self, msg: str) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(self._channel_id)
        max_length = 2000
        # We break the message and send it in chunks in case it exceeds the max allowed limit.
        # Note that this is bad as it will break formatting. Splitting is done by chars and not
        # words.
        for chunk in chunks(msg, max_length):
            await channel.send(chunk)

    async def send_file(self, path: str) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(self._channel_id)
        await channel.send(file=discord.File(path))
