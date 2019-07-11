import asyncio
import logging
from enum import Enum
from typing import Any, Awaitable, Callable, Dict

from juno.asyncio import empty_future
from juno.typing import filter_member_args
from juno.utils import EventEmitter, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()


class Agent:

    run: Callable[..., Awaitable[None]] = lambda: empty_future()

    def __init__(self) -> None:
        self.ee = EventEmitter()
        self.state = AgentState.STOPPED
        self.result: Any = None
        self.name = next(_random_names)

    async def start(self, agent_config: Dict[str, Any]) -> Any:
        assert self.state is not AgentState.RUNNING

        await self.ee.emit('starting', agent_config)

        self.state = AgentState.RUNNING
        type_name = type(self).__name__.lower()
        _log.info(f'running {self.name} ({type_name}): {agent_config}')
        try:
            await self.run(**filter_member_args(self.run, agent_config))
        except asyncio.CancelledError:
            _log.info('agent cancelled')
        except Exception as e:
            _log.exception('unhandled exception in agent')
            await self.ee.emit('errored', e)
            raise

        _log.info('finalizing')
        await self.finalize()

        self.state = AgentState.STOPPED
        _log.info(f'{self.name} ({type_name}) finished: {self.result}')
        await self.ee.emit('finished')

        return self.result

    async def finalize(self) -> None:
        pass


class AgentState(Enum):
    STOPPED = 0
    RUNNING = 1
