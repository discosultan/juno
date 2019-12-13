import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from juno.agents import Agent, Backtest

_log = logging.getLogger(__name__)


@asynccontextmanager
async def activate(agent: Agent, plugin_config: Dict[str, Any]) -> AsyncIterator[None]:
    if not isinstance(agent, Backtest):
        raise NotImplementedError()

    @agent.on('finished')
    async def on_finished() -> None:
        pass
        # export summary as csv

    _log.info('activated')
    yield
