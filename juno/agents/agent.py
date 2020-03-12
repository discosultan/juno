from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Generic, List, TypeVar

from juno.components import Event
from juno.plugins import Plugin
from juno.utils import generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()

T = TypeVar('T')


class AgentStatus(IntEnum):
    RUNNING = 0
    CANCELLED = 1
    ERRORED = 2
    FINISHED = 3


class Agent:
    class Config:
        pass

    @dataclass
    class State(Generic[T]):
        name: str
        status: AgentStatus
        result: T

    def __init__(self, event: Event = Event()) -> None:
        self._event = event

    async def run(self, config: Any, plugins: List[Plugin] = []) -> Agent.State:
        state: Agent.State[Any] = Agent.State(
            name=getattr(config, 'name', None) or f'{next(_random_names)}-{uuid.uuid4()}',
            status=AgentStatus.RUNNING,
            result=None,
        )
        type_name = type(self).__name__.lower()

        # Activate plugins.
        await asyncio.gather(*(p.activate(state.name, type_name) for p in plugins))

        await self._event.emit(state.name, 'starting', config)
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
            await self._event.emit(state.name, 'errored', exc, state.result)
            raise
        else:
            state.status = AgentStatus.FINISHED
        finally:
            await self.on_finally(config, state)

        await self._event.emit(state.name, 'finished', state.result)

        return state

    async def on_running(self, config: Any, state: Any) -> None:
        pass

    async def on_cancelled(self, config: Any, state: Any) -> None:
        pass

    async def on_errored(self, config: Any, state: Any) -> None:
        pass

    async def on_finally(self, config: Any, state: Any) -> None:
        pass
