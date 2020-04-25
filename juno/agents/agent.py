from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Generic, List, TypeVar

from juno.components import Event
from juno.plugins import Plugin
from juno.storages import Memory, Storage
from juno.utils import exc_traceback, format_as_config, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()

T = TypeVar('T')


class AgentStatus(IntEnum):
    RUNNING = 0
    CANCELLED = 1
    ERRORED = 2
    FINISHED = 3


class Agent:
    _event: Event
    _storage: Storage

    class Config:
        pass

    @dataclass
    class State(Generic[T]):
        name: str
        status: AgentStatus
        result: T

    def __init__(self, event: Event = Event(), storage: Storage = Memory()) -> None:
        self._event = event
        self._storage = storage

    async def run(self, config: Any, plugins: List[Plugin] = []) -> T:
        state = await self._get_or_create_state(config)

        # Activate plugins.
        type_name = type(self).__name__.lower()
        await asyncio.gather(*(p.activate(state.name, type_name) for p in plugins))
        _log.info(
            f'{self._get_name(state)}: activated plugins '
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
        _log.info(f'{self._get_name(state)}: running with config {format_as_config(config)}')
        await self._event.emit(state.name, 'starting', config)

    async def on_cancelled(self, config: Any, state: Any) -> None:
        _log.info(f'{self._get_name(state)}: cancelled')
        await self._event.emit(state.name, 'cancelled')

    async def on_errored(self, config: Any, state: Any, exc: Exception) -> None:
        _log.error(f'{self._get_name(state)}: unhandled exception {exc_traceback(exc)}')
        await self._event.emit(state.name, 'errored', exc)

    async def on_finally(self, config: Any, state: Any) -> None:
        _log.info(
            f'{self._get_name(state)}: finished with result {format_as_config(state.result)}'
        )
        await self._event.emit(state.name, 'finished', state.result)

    async def _get_or_create_state(self, config: Any) -> Agent.State:
        name = getattr(config, 'name', None) or f'{next(_random_names)}-{uuid.uuid4()}'
        result_type = self._get_result_type(config)

        if getattr(config, 'persist', False):
            # TODO: walrus
            existing_state = await self._storage.get(
                'default',
                self._get_storage_key(name),
                Agent.State[self._get_result_type(config)],  # type: ignore
            )
            if existing_state:
                if existing_state.status is AgentStatus.FINISHED:
                    raise NotImplementedError(
                        f'Cannot continue existing session {existing_state.name} from '
                        f'{AgentStatus.FINISHED.name} status'
                    )

                _log.info(
                    f'existing live session {existing_state.name} found; continuing from '
                    f'{existing_state.status} status'
                )
                return existing_state
            else:
                _log.info(f'existing state with name {name} not found; creating new')
        else:
            _log.info(f'creating new state')

        return Agent.State(
            name=name,
            status=AgentStatus.RUNNING,
            result=result_type(),
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

    def _get_result_type(self, config: Any) -> type:
        return type(None)

    def _get_storage_key(self, name: str) -> str:
        return f'{type(self).__name__.lower()}_{name}_state'

    def _get_name(self, state: Any) -> str:
        return f'{state.name} ({type(self).__name__.lower()})'
