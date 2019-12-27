import asyncio
import logging
import traceback
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List

from juno.asyncio import empty_future
from juno.utils import EventEmitter, format_attrs_as_json, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()


class Agent(EventEmitter):

    run: Callable[..., Awaitable[None]] = lambda: empty_future()

    def __init__(self) -> None:
        super().__init__()
        self.state = AgentState.STOPPED
        self.result: Any = None
        self.config: Dict[str, Any] = {}
        self.name = next(_random_names)

    async def start(self, **agent_config: Any) -> Any:
        assert self.state is not AgentState.RUNNING

        self.config = agent_config
        if 'name' in agent_config:
            self.name = agent_config['name']

        await self.emit('starting')

        self.state = AgentState.RUNNING
        type_name = type(self).__name__.lower()
        _log.info(f'running {self.name} ({type_name}): {agent_config}')
        try:
            await self.run(**agent_config)
        except asyncio.CancelledError:
            _log.info('agent cancelled')
        except Exception as exc:
            _log.error(f'unhandled exception in agent ({exc})')
            await self.emit('errored', exc)
            raise

        _log.info('finalizing')
        await self.finalize()

        self.state = AgentState.STOPPED
        _log.info(f'{self.name} ({type_name}) finished:\n{format_attrs_as_json(self.result)}')
        await self.emit('finished')

        return self.result

    async def finalize(self) -> None:
        pass

    async def emit(self, event: str, *args: Any) -> List[Any]:
        results = await super().emit(event, *args)
        for e in (r for r in results if isinstance(r, Exception)):
            _log.error(''.join(traceback.format_exception(type(e), e, e.__traceback__)))
        return results


class AgentState(Enum):
    STOPPED = 0
    RUNNING = 1
