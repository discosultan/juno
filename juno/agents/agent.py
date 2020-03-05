import asyncio
import logging
import uuid
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List

from juno.asyncio import resolved_future
from juno.components import Event
from juno.utils import exc_traceback, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()


class Agent:

    run: Callable[..., Awaitable[None]] = lambda: resolved_future(None)

    def __init__(self, event: Event = Event()) -> None:
        self._event = event
        self.status = AgentStatus.RUNNING
        self.result: Any = None
        self.config: Dict[str, Any] = {}
        self.name = f'{next(_random_names)}-{uuid.uuid4()}'

    async def start(self, **agent_config: Any) -> Any:
        self.config = agent_config
        self.name = agent_config.get('name', self.name)

        await self.emit('starting')
        type_name = type(self).__name__.lower()
        _log.info(f'running {self.name} ({type_name}): {agent_config}')

        try:
            await self.run(**agent_config)
        except asyncio.CancelledError:
            _log.info('agent cancelled')
            self.status = AgentStatus.CANCELLED
            await self.on_cancelled()
        except Exception as exc:
            _log.error(f'unhandled exception in agent ({exc})')
            self.status = AgentStatus.ERRORED
            await self.on_errored()
            await self.emit('errored', exc)
            raise
        else:
            self.status = AgentStatus.FINISHED
        finally:
            await self.on_finally()

        await self.emit('finished')
        return self.result

    def on(self, event: str) -> Callable[[Callable[..., Awaitable[None]]], None]:
        return self._event.on(self.name, event)

    async def emit(self, event: str, *args: Any) -> List[Any]:
        results = await self._event.emit(self.name, event, *args)
        for e in (r for r in results if isinstance(r, Exception)):
            _log.error(exc_traceback(e))
        return results

    async def on_cancelled(self) -> None:
        pass

    async def on_errored(self) -> None:
        pass

    async def on_finally(self) -> None:
        pass


class AgentStatus(Enum):
    RUNNING = 0
    CANCELLED = 1
    ERRORED = 2
    FINISHED = 3
