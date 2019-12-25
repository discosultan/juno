from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import discord

from juno import json
from juno.agents import Agent
from juno.asyncio import cancel, cancelable
from juno.trading import Position
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import chunks, format_attrs_as_json

_log = logging.getLogger(__name__)


@asynccontextmanager
async def activate(agent: Agent, plugin_config: Dict[str, Any]) -> AsyncIterator[None]:
    def format_message(title: str, content: str, lang: str = 'json') -> str:
        return f'{type(agent).__name__} agent {agent.name} {title}:\n```{lang}\n{content}\n```\n'

    async with Discord(
        token=plugin_config['token'],
        channel_id=plugin_config['channel_id'][type(agent).__name__.lower()]
    ) as client:

        @agent.on('starting')
        async def on_starting() -> None:
            await client.send_message(
                format_message('starting with config', json.dumps(agent.config, indent=4))
            )

        @agent.on('position_opened')
        async def on_position_opened(pos: Position) -> None:
            # We send separate messages to avoid exhausting max message length limit.
            await client.send_message(format_message('opened position', format_attrs_as_json(pos)))
            await client.send_message(
                format_message('summary', format_attrs_as_json(agent.result))
            )

        @agent.on('position_closed')
        async def on_position_closed(pos: Position) -> None:
            await client.send_message(format_message('closed position', format_attrs_as_json(pos)))
            await client.send_message(
                format_message('summary', format_attrs_as_json(agent.result))
            )

        @agent.on('finished')
        async def on_finished() -> None:
            await client.send_message(
                format_message('finished with summary', format_attrs_as_json(agent.result))
            )

        @agent.on('errored')
        async def on_errored(exc: Exception) -> None:
            msg = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            await client.send_message(format_message('errored', msg, lang=''))
            await client.send_message(
                format_message('summary', format_attrs_as_json(agent.result))
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
