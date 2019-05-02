from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import EventEmitter, gen_random_names

_EXCLUDE_FROM_CONFIG = ['name', 'plugins']

_log = logging.getLogger(__name__)

_random_names = gen_random_names()


class Agent:

    required_components: List[str] = []
    run: Callable[..., Awaitable[None]]

    def __init__(self, components: Dict[str, Any], agent_config: Dict[str, Any]) -> None:
        self.components = components
        self.config = agent_config
        self.state = 'stopped'
        self.result: Any = None
        self.name = next(_random_names)

    # TODO: Make use of __aenter__ and __aexit__ instead?
    async def __aenter__(self) -> Agent:
        self.ee = EventEmitter()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    async def start(self) -> Any:
        assert self.state != 'running'

        await self.ee.emit('starting', self)

        self.state = 'running'
        type_name = type(self).__name__.lower()
        _log.info(f'running {self.name} ({type_name}): {self.config}')
        try:
            await self.run(
                **{k: v for k, v in self.config.items() if k not in _EXCLUDE_FROM_CONFIG})
        except asyncio.CancelledError:
            _log.info('agent cancelled')
        except Exception:
            _log.exception('unhandled exception in agent')
            raise
        self.state = 'stopped'
        _log.info(f'{self.name} ({type_name}) finished: {self.result}')

        await self.finalize()

        await self.ee.emit('finished')

        return self.result

    async def finalize(self) -> None:
        pass
