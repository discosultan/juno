from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from more_itertools import sliced
from slack_sdk.web.async_client import AsyncWebClient

from juno import Advice
from juno.components import Events
from juno.config import format_as_config
from juno.traders import Trader
from juno.trading import Position, TradingSummary
from juno.utils import exc_traceback, extract_public

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Slack(Plugin):
    def __init__(self, events: Events, config: dict[str, Any]) -> None:
        slack_config = config.get(type(self).__name__.lower(), {})
        if not (token := slack_config.get('token')):
            raise ValueError('Missing token from config')
        if not (channel_id := slack_config.get('channel_id')):
            raise ValueError('Missing channel ID from config')

        self._slack_client = AsyncWebClient(token=token)
        self._events = events
        self._token = token
        self._channel_id = channel_id

    async def activate(self, agent_name: str, agent_type: str) -> None:
        agent_state = None

        send_message = partial(self._send_message, self._channel_id)
        format_message = partial(self._format_message, agent_name)

        await self._slack_client.conversations_join(channel=self._channel_id)

        @self._events.on(agent_name, 'starting')
        async def on_starting(config: Any, state: Any, trader: Trader) -> None:
            nonlocal agent_state
            agent_state = state
            await send_message(format_message('starting with config', format_as_config(config)))

        @self._events.on(agent_name, 'positions_opened')
        async def on_positions_opened(positions: list[Position], summary: TradingSummary) -> None:
            await asyncio.gather(
                *(send_message(
                    format_message(
                        f'opened {"long" if isinstance(p, Position.OpenLong) else "short"} '
                        'position',
                        format_as_config(extract_public(p, exclude=['fills'])),
                    ),
                ) for p in positions)
            )

        @self._events.on(agent_name, 'positions_closed')
        async def on_positions_closed(positions: list[Position], summary: TradingSummary) -> None:
            # We send separate messages to avoid exhausting max message length limit.
            await asyncio.gather(
                *(send_message(
                    format_message(
                        f'closed {"long" if isinstance(p, Position.Long) else "short"} '
                        'position',
                        format_as_config(extract_public(p, exclude=['open_fills', 'close_fills'])),
                    ),
                ) for p in positions)
            )
            await send_message(
                format_message('summary', format_as_config(extract_public(summary)))
            )

        @self._events.on(agent_name, 'finished')
        async def on_finished(summary: TradingSummary) -> None:
            await send_message(
                format_message(
                    'finished with summary', format_as_config(extract_public(summary)),
                ),
            )

        @self._events.on(agent_name, 'errored')
        async def on_errored(exc: Exception) -> None:
            await send_message(format_message('errored', exc_traceback(exc)))

        @self._events.on(agent_name, 'advice')
        async def on_advice(advice: Advice) -> None:
            await send_message(format_message('received advice', advice.name))

        _log.info(f'activated for {agent_name} ({agent_type})')

    async def _send_message(self, channel: str, msg: str) -> None:
        max_length = 40000
        # We break the message and send it in chunks in case it exceeds the max allowed limit.
        # Note that this is bad as it will break formatting. Splitting is done by chars and not
        # words.
        for msg_slice in sliced(msg, max_length):
            await self._slack_client.chat_postMessage(channel=channel, text=msg_slice)

    def _format_message(self, agent_name: str, title: str, content: Any) -> str:
        return f'Agent {agent_name} {title}:\n```\n{content}\n```\n'
