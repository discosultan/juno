import asyncio
import logging
import traceback
from enum import Enum
from typing import Any, Awaitable, Callable, Tuple

from juno.asyncio import empty_future
from juno.typing import filter_member_args
from juno.utils import EventEmitter, generate_random_words

_log = logging.getLogger(__name__)

_random_names = generate_random_words()


class Agent(EventEmitter):

    run: Callable[..., Awaitable[None]] = lambda: empty_future()

    def __init__(self) -> None:
        super().__init__()
        self.state = AgentState.STOPPED
        self.result: Any = None
        self.name = next(_random_names)

    async def start(self, **agent_config: Any) -> Any:
        assert self.state is not AgentState.RUNNING

        await self.emit('starting', agent_config)

        self.state = AgentState.RUNNING
        type_name = type(self).__name__.lower()
        _log.info(f'running {self.name} ({type_name}): {agent_config}')
        try:
            await self.run(**filter_member_args(self.run, agent_config))
        except asyncio.CancelledError:
            _log.info('agent cancelled')
        except Exception as exc:
            _log.exception('unhandled exception in agent')
            await self.emit('errored', exc)
            raise

        _log.info('finalizing')
        await self.finalize()

        self.state = AgentState.STOPPED
        _log.info(f'{self.name} ({type_name}) finished: {self.result}')
        await self.emit('finished')

        return self.result

    async def finalize(self) -> None:
        pass

    async def emit(self, event: str, *args: Any) -> Tuple[Any, ...]:
        results = await super().emit(event, *args)
        for e in (r for r in results if isinstance(r, Exception)):
            _log.error(''.join(traceback.format_exception(type(e), e, e.__traceback__)))
        return results


class AgentState(Enum):
    STOPPED = 0
    RUNNING = 1
