import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack
from types import FrameType
from typing import Any, Dict, List

import juno
from juno.config import load_all_types, load_from_env, load_from_json_file, load_type
from juno.di import Container
from juno.exchanges import Exchange
from juno.plugins import list_plugins
from juno.storages import Storage
from juno.utils import map_module_types

_log = logging.getLogger(__name__)


async def engine() -> None:
    try:
        # Load config.
        config_path = 'config.json'
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        config = {}
        config.update(load_from_json_file(config_path))
        config.update(load_from_env())

        # Configure logging.
        log_level = config.get('log_level', 'INFO').upper()
        logging.basicConfig(
            handlers=[logging.StreamHandler(stream=sys.stdout)],
            level=logging.getLevelName(log_level))
        _log.info(f'log level set to: {log_level}')

        # Configure signals.
        def handle_sigterm(signalnum: int, frame: FrameType) -> None:
            _log.info(f'SIGTERM terminating the process')
            sys.exit()
        signal.signal(signal.SIGTERM, handle_sigterm)

        # Configure deps.
        container = Container()
        container.add_singleton(Dict[str, Any], config)
        container.add_singleton(Storage, load_type(config, Storage))
        container.add_singleton(List[Exchange], load_all_types(config, Exchange))

        # Load agents.
        agent_types = map_module_types(juno.agents)
        agent_config_map = {container.resolve(agent_types[c['name']]): c for c
                            in config['agents']}

        # Load plugins.
        plugins = list_plugins(agent_config_map, config)

        async with AsyncExitStack() as stack:

            # Init all deps and plugins.
            await asyncio.gather(
                stack.enter_async_context(container),
                *(stack.enter_async_context(p) for p in plugins))

            # Run agents.
            await asyncio.gather(*(a.start(c) for a, c in agent_config_map))

        _log.info('main finished')
    except asyncio.CancelledError:
        _log.info('main task cancelled')
    except Exception:
        _log.exception('unhandled exception in main')
        raise


try:
    asyncio.run(engine())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
