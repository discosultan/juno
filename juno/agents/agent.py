from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, List

from juno.components import Event
from juno.utils import exc_traceback, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()


class AgentStatus(IntEnum):
    RUNNING = 0
    CANCELLED = 1
    ERRORED = 2
    FINISHED = 3


class Agent:
    @dataclass
    class State:
        status: AgentStatus
        name: str
        result: Any = None

    def __init__(self, event: Event = Event()) -> None:
        self._event = event

    async def run(self, config: Any) -> Agent.State:
        state = Agent.State(
            status=AgentStatus.RUNNING,
            name=getattr(config, 'name', None) or f'{next(_random_names)}-{uuid.uuid4()}',
        )

        await self.emit(state.name, 'starting')
        type_name = type(self).__name__.lower()
        _log.info(f'running {state.name} ({type_name}): {config}')

        try:
            await self.on_running(config, state)
        except asyncio.CancelledError:
            _log.info('agent cancelled')
            state.status = AgentStatus.CANCELLED
            await self.on_cancelled(config, state)
        except Exception as exc:
            _log.error(f'unhandled exception in agent ({exc})')
            state.status = AgentStatus.ERRORED
            await self.on_errored(config, state)
            await self.emit(state.name, 'errored', exc)
            raise
        else:
            state.status = AgentStatus.FINISHED
        finally:
            await self.on_finally(config, state)

        await self.emit(state.name, 'finished')

        return state

    async def on_running(self, config: Any, state: Any) -> None:
        pass

    async def on_cancelled(self, config: Any, state: Any) -> None:
        pass

    async def on_errored(self, config: Any, state: Any) -> None:
        pass

    async def on_finally(self, config: Any, state: Any) -> None:
        pass

    async def emit(self, channel: str, event: str, *args: Any) -> List[Any]:
        results = await self._event.emit(channel, event, *args)
        for e in (r for r in results if isinstance(r, Exception)):
            _log.error(exc_traceback(e))
        return results
