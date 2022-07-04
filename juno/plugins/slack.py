from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from more_itertools import sliced
from slack_sdk.web.async_client import AsyncWebClient

from juno import json, serialization
from juno.components import Events
from juno.traders import Trader
from juno.trading import Position, TradingSummary
from juno.utils import exc_traceback, extract_public

from .plugin import Plugin

_log = logging.getLogger(__name__)


class Slack(Plugin):
    def __init__(self, events: Events, config: dict[str, Any]) -> None:
        slack_config = config.get(type(self).__name__.lower(), {})

        if not (token := slack_config.get("token")):
            raise ValueError("Missing token from config")
        if not isinstance(token, str):
            raise ValueError("Token should be a string")

        channel_ids = slack_config.get("channel_id", {})
        if not isinstance(channel_ids, dict):
            raise ValueError(
                f"Channel IDs should be a map but was a {type(channel_ids).__name__} instead"
            )

        self._slack_client = AsyncWebClient(token=token)
        self._events = events
        self._token = token
        self._channel_ids = channel_ids

    async def activate(self, agent_name: str, agent_type: str) -> None:
        channel_name = agent_type
        if not (channel_id := self._channel_ids.get(channel_name)):
            raise ValueError(f"Missing {channel_name} channel ID from config")

        agent_state = None

        send_message = partial(self._send_message, channel_id)
        format_message = partial(self._format_message, agent_name)

        await self._slack_client.conversations_join(channel=channel_id)

        @self._events.on(agent_name, "starting")
        async def on_starting(config: Any, state: Any, trader: Trader) -> None:
            nonlocal agent_state
            agent_state = state
            await send_message(
                format_message(
                    "starting with config",
                    json.dumps(serialization.config.serialize(config), indent=4),
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
                        ),
                    )
                    for p in positions
                )
            )
            await send_message(
                format_message(
                    "summary",
                    json.dumps(serialization.config.serialize(extract_public(summary)), indent=4),
                )
            )

        @self._events.on(agent_name, "finished")
        async def on_finished(summary: TradingSummary) -> None:
            await send_message(
                format_message(
                    "finished with summary",
                    json.dumps(serialization.config.serialize(extract_public(summary)), indent=4),
                ),
            )

        @self._events.on(agent_name, "errored")
        async def on_errored(exc: Exception) -> None:
            await send_message(format_message("errored", exc_traceback(exc)))

        @self._events.on(agent_name, "message")
        async def on_message(message: str) -> None:
            await send_message(format_message("received message", message))

        _log.info(f"activated for {agent_name} ({agent_type})")

    async def _send_message(self, channel: str, msg: str) -> None:
        max_length = 40000
        # We break the message and send it in chunks in case it exceeds the max allowed limit.
        # Note that this is bad as it will break formatting. Splitting is done by chars and not
        # words.
        for msg_slice in sliced(msg, max_length):
            await self._slack_client.chat_postMessage(
                channel=channel,
                text=msg_slice,  # type: ignore
            )

    def _format_message(self, agent_name: str, title: str, content: Any) -> str:
        return f"Agent {agent_name} {title}:\n```\n{content}\n```\n"
