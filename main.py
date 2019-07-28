import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack
from types import FrameType
from typing import Any, Dict, List

import juno
from juno.asyncio import cancelable
from juno.agents import Agent
from juno.brokers import Broker
from juno.config import (
    load_from_env, load_from_json_file, load_instance, load_instances, load_type
)
from juno.di import Container
from juno.exchanges import Exchange
from juno.logging import create_handler
from juno.plugins import list_plugins
from juno.storages import Storage
from juno.utils import map_module_types

_log = logging.getLogger(__name__)


async def main() -> None:
    # Load config.
    config_name = sys.argv[1] if len(sys.argv) >= 2 else 'default'
    config = {}
    config.update(load_from_json_file(f'config/{config_name}.json'))
    config.update(load_from_env())

    # Configure logging.
    log_level = config.get('log_level', 'info')
    log_format = config.get('log_format', 'default')
    logging.basicConfig(
        handlers=[create_handler(log_format)], level=logging.getLevelName(log_level.upper())
    )
    _log.info(f'log level: {log_level}; format: {log_format}')

    # Configure signals.
    def handle_sigterm(signalnum: int, frame: FrameType) -> None:
        _log.info(f'SIGTERM terminating the process')
        sys.exit()

    signal.signal(signal.SIGTERM, handle_sigterm)

    # Configure deps.
    container = Container()
    container.add_singleton_instance(Dict[str, Any], lambda: config)
    container.add_singleton_instance(Storage, lambda: load_instance(Storage, config))
    container.add_singleton_instance(List[Exchange], lambda: load_instances(Exchange, config))
    container.add_singleton_type(Broker, lambda: load_type(Broker, config))

    # Load agents.
    agent_types = map_module_types(juno.agents)
    agent_config_map: Dict[Agent, Dict[str, Any]] = {
        container.resolve(agent_types[c['name']]): c
        for c in config['agents']
    }

    # Load plugins.
    plugins = list_plugins(agent_config_map, config)

    async with AsyncExitStack() as stack:

        # Init all deps and plugins.
        await asyncio.gather(
            stack.enter_async_context(container),
            *(stack.enter_async_context(p) for p in plugins)
        )

        # Run agents.
        await asyncio.gather(*(a.start(**c) for a, c in agent_config_map.items()))

    _log.info('main finished')


try:
    asyncio.run(cancelable(main()))
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
except BaseException:
    _log.exception('unhandled error in program')
finally:
    _log.info('program exiting')
