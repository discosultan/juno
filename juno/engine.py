import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack
from types import FrameType
from typing import Any, Dict, List

import juno
from juno.agents import map_agent_types
from juno.config import init_type, list_names, load_from_env, load_from_json_file
from juno.plugins import list_plugins
from juno.utils import list_deps_in_init_order, map_dependencies

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
        signal.signal(signal.SIGTERM, handle_sigterm)

        agent_type_map = map_agent_types(config)

        def resolve_abstract(abstract: type, candidates: List[type]) -> List[type]:
            abstract_name = abstract.__name__.lower()
            return [c for c in candidates if
                    c.__name__.lower() in list_names(config, abstract_name)]

        # Setup components used by agents.
        dep_map = map_dependencies(
            agent_type_map.values(),
            [juno.brokers, juno.components, juno.exchanges, juno.storages],
            resolve_abstract)

        async with AsyncExitStack() as stack:
            components: Dict[str, Any] = {}
            for deps in list_deps_in_init_order(dep_map):
                to_init = []
                for dep in (dep for dep in deps if dep not in agent_type_map.values()):
                    component = init_type(dep, components, config)
                    components[dep.__name__.lower()] = component
                    to_init.append(component)
                await asyncio.gather(*(stack.enter_async_context(c) for c in to_init))

            # Setup agents.
            agent_config_map = {
                init_type(
                    agent_type_map[agent_config['name']],
                    components,
                    {}): agent_config for agent_config in config['agents']
            }
            await asyncio.gather(
                *(stack.enter_async_context(agent) for agent in agent_config_map.keys()))

            # Setup plugins.
            plugins = list_plugins(agent_config_map.items(), config)
            await asyncio.gather(*(stack.enter_async_context(p) for p in plugins))

            # Run configured agents.
            await asyncio.gather(*(agent.start(ac) for agent, ac in agent_config_map.items()))

        _log.info('main finished')
    except asyncio.CancelledError:
        _log.info('main task cancelled')
    except Exception:
        _log.exception('unhandled exception in main')
        raise


def handle_sigterm(signalnum: int, frame: FrameType) -> None:
    _log.info(f'SIGTERM terminating the process')
    sys.exit()


try:
    asyncio.run(engine())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
