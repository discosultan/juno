import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack
from types import FrameType
from typing import Any, Dict, List

from juno import components, exchanges, storages
from juno.agents import map_agent_types
from juno.config import list_required_names, load_from_env, load_from_json_file
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

        # # Create configured services.
        # services = {}
        # services.update(map_exchanges(config, list_required_names(config, 'exchange')))
        # services.update(map_storages(config, list_required_names(config, 'storage')))
        # _log.info(f'services created: {", ".join(services.keys())}')

        # # Create components used by configured agents.
        # components = map_components(services, config, list_required_component_names(config))
        # _log.info(f'components created: {", ".join(components.keys())}')

        # # Create configured agents.
        # agents = list_agents(components, config)

        # # Load plugins.
        # plugins = list_plugins(agents, config)

        def initialize(type_: type, dep_map: Dict[type, List[type]], instances: Dict[type, Any],
                       config: Dict[str, Any]) -> Any:
            return dep(
                **{t.__name__.lower(): instances[t] for t in dep_map[type_]},
                **config.get(type_.__name__.lower(), {}))

        # TEMP START
        agent_type_map = map_agent_types(config)
        dep_map = map_dependencies(agent_type_map.values(), [components, exchanges, storages])
        async with AsyncExitStack() as stack:
            component_instances: Dict[type, Any] = {}
            for deps in list_deps_in_init_order(dep_map):
                deps = (dep for dep in deps if dep not in agent_type_map.values())
                for dep in deps:
                    component_instances[dep] = initialize(dep, dep_map, component_instances,
                                                          config)
                await asyncio.gather(
                    *(stack.enter_async_context(component_instances[dep]) for t in deps))

            agent_config_map = {
                initialize(agent_type_map[agent_config['name']], dep_map, component_instances, {}):
                agent_config for agent_config in config['agents']}

            await asyncio.gather(
                *(stack.enter_async_context(agent) for agent in agent_config_map.keys()))

            # Run configured agents.
            await asyncio.gather(*(agent.start(ac) for agent, ac in agent_config_map.items()))
        # TEMP END

        # async with AsyncExitStack() as stack:
        #     # Init services.
        #     await asyncio.gather(*(stack.enter_async_context(s) for s in services.values()))
        #     # Init components.
        #     await asyncio.gather(*(stack.enter_async_context(c) for c in components.values()))
        #     # Init agents.
        #     await asyncio.gather(*(stack.enter_async_context(a) for a in agents))
        #     # Init plugins.
        #     await asyncio.gather(*(stack.enter_async_context(p) for p in plugins))
        #     # Run configured agents.
        #     await asyncio.gather(*(a.start() for a in agents))

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
