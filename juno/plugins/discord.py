from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, AsyncIterator, Dict, Type

import discord
import simplejson as json

from juno.agents import Agent
from juno.agents.summary import Position
from juno.asyncio import cancel, cancelable
from juno.typing import ExcType, ExcValue, Traceback


_log = logging.getLogger(__name__)


@asynccontextmanager
async def activate(agent: Agent, plugin_config: Dict[str, Any]) -> AsyncIterator[None]:
    def format_action(action: str) -> str:
        return f'{type(agent).__name__} agent {agent.name} {action}.\n'

    def format_block(title: str, content: str, lang: str = '') -> str:
        return f'{title}:\n```{lang}\n{content}\n```\n'

    async with Discord(
        token=plugin_config['token'],
        channel_id=plugin_config['channel_id'][type(agent).__name__.lower()]
    ) as client:

        @agent.ee.on('starting')
        async def on_starting(agent_config: Dict[str, Any]) -> None:
            await client.send_message(
                format_action('starting') +
                format_block('Config', json.dumps(agent_config, indent=4), lang='json')
            )

        @agent.ee.on('position_opened')
        async def on_position_opened(pos: Position) -> None:
            await client.send_message(
                format_action('opened a position') + format_block('Position', str(pos)) +
                format_block('Summary', str(agent.result))
            )

        @agent.ee.on('position_closed')
        async def on_position_closed(pos: Position) -> None:
            await client.send_message(
                format_action('closed a position') + format_block('Position', str(pos)) +
                format_block('Summary', str(agent.result))
            )

        @agent.ee.on('finished')
        async def on_finished() -> None:
            await client.send_message(
                format_action('finished') + format_block('Summary', str(agent.result))
            )

        @agent.ee.on('errored')
        async def on_errored(
            exc_type: Type[BaseException], exc_value: BaseException, tb: TracebackType
        ) -> None:
            exc_msg_list = traceback.format_exception(exc_type, exc_value, tb)
            await client.send_message(
                format_action('errored') + format_block('Exception', ''.join(exc_msg_list)) +
                format_block('Summary', str(agent.result))
            )

        @agent.ee.on('image')
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

    async def send_message(self, msg: Any) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(self._channel_id)
        await channel.send(msg)

    async def send_file(self, path: str) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(self._channel_id)
        await channel.send(file=discord.File(path))
