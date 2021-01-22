from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Optional

from juno.components import Events
from juno.config import format_as_config
from juno.plugins import Plugin
from juno.storages import Memory, Storage
from juno.utils import exc_traceback, extract_public, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()


class AgentStatus(IntEnum):
    RUNNING = 0
    CANCELLED = 1
    ERRORED = 2
    FINISHED = 3


class Agent:
    _events: Events
    _storage: Storage

    class Config:
        pass

    @dataclass
    class State:
        name: str
        status: AgentStatus
        result: Optional[Any] = None

    def __init__(self, events: Events = Events(), storage: Storage = Memory()) -> None:
        self._events = events
        self._storage = storage

    async def run(self, config: Any, plugins: list[Plugin] = []) -> Any:
        state = await self._get_or_create_state(config)

        # Activate plugins.
        type_name = type(self).__name__.lower()
        await asyncio.gather(*(p.activate(state.name, type_name) for p in plugins))
        _log.info(
            f'{self.get_name(state)}: activated plugins '
            f'[{", ".join(type(p).__name__.lower() for p in plugins)}]'
        )

        try:
            await self.on_running(config, state)
            state.status = AgentStatus.FINISHED
        except asyncio.CancelledError:
            state.status = AgentStatus.CANCELLED
            await self.on_cancelled(config, state)
        except Exception as exc:
            state.status = AgentStatus.ERRORED
            await self.on_errored(config, state, exc)
            raise
        finally:
            await self._try_save_state(config, state)
            await self.on_finally(config, state)

        return state.result

    async def on_running(self, config: Any, state: Any) -> None:
        _log.info(f'{self.get_name(state)}: running with config {format_as_config(config)}')
        await self._events.emit(state.name, 'starting', config, state)

    async def on_cancelled(self, config: Any, state: Any) -> None:
        _log.info(f'{self.get_name(state)}: cancelled')
        await self._events.emit(state.name, 'cancelled')

    async def on_errored(self, config: Any, state: Any, exc: Exception) -> None:
        _log.error(f'{self.get_name(state)}: unhandled exception {exc_traceback(exc)}')
        await self._events.emit(state.name, 'errored', exc)

    async def on_finally(self, config: Any, state: Any) -> None:
        _log.info(
            f'{self.get_name(state)}: finished with result '
            f'{format_as_config(extract_public(state.result))}'
        )
        await self._events.emit(state.name, 'finished', state.result)

    def get_name(self, state: Any) -> str:
        return f'{state.name} ({type(self).__name__.lower()})'

    async def _get_or_create_state(self, config: Any) -> Agent.State:
        name = getattr(config, 'name', None) or f'{next(_random_names)}-{uuid.uuid4()}'
        state_type = type(self).State

        if getattr(config, 'persist', False):
            existing_state = await self._storage.get(
                'default',
                self._get_storage_key(name),
                state_type,
            )
            if existing_state:
                if existing_state.status is AgentStatus.FINISHED:
                    raise NotImplementedError(
                        f'Cannot continue existing session {existing_state.name} from '
                        f'{AgentStatus.FINISHED.name} status'
                    )

                _log.info(
                    f'existing live session {existing_state.name} found; continuing from '
                    f'{existing_state.status.name} status'
                )
                return existing_state
            else:
                _log.info(f'existing state with name {name} not found; creating new')
        else:
            _log.info('creating new state')

        return state_type(
            name=name,
            status=AgentStatus.RUNNING,
        )

    async def _try_save_state(self, config: Config, state: Agent.State) -> None:
        if getattr(config, 'persist', False):
            _log.info(
                f'storing current state with name {state.name} and status {state.status.name}'
            )
            await self._storage.set(
                'default',
                self._get_storage_key(state.name),
                state,
            )

    def _get_storage_key(self, name: str) -> str:
        return f'{type(self).__name__.lower()}_{name}_state'
