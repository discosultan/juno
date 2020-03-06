import asyncio
import logging
import uuid
from abc import ABC
from enum import IntEnum
from typing import Any, Generic, List, Optional, TypeVar

from juno.components import Event
from juno.utils import exc_traceback, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()


class AgentConfig(ABC):
    name: Optional[str]


class AgentStatus(IntEnum):
    RUNNING = 0
    CANCELLED = 1
    ERRORED = 2
    FINISHED = 3


class AgentState(ABC):
    status: AgentStatus
    name: str


TConfig = TypeVar('TConfig', bound=AgentConfig)
TState = TypeVar('TState', bound=AgentState)


class Agent(Generic[TConfig, TState]):

    def __init__(self, event: Event = Event()) -> None:
        self._event = event

    async def run(self, config: TConfig) -> None:
        state = TState(  # type: ignore
            status=AgentStatus.RUNNING,
            name=config.name or f'{next(_random_names)}-{uuid.uuid4()}',
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

    async def on_running(self, config: TConfig, state: TState) -> None:
        pass

    async def on_cancelled(self, config: TConfig, state: TState) -> None:
        pass

    async def on_errored(self, config: TConfig, state: TState) -> None:
        pass

    async def on_finally(self, config: TConfig, state: TState) -> None:
        pass

    async def emit(self, channel: str, event: str, *args: Any) -> List[Any]:
        results = await self._event.emit(channel, event, *args)
        for e in (r for r in results if isinstance(r, Exception)):
            _log.error(exc_traceback(e))
        return results
