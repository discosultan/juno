import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack
from types import FrameType

from juno.agents import Agent, list_agents, list_required_component_names
from juno.components import map_components
from juno.config import list_required_names, load_from_env, load_from_json_file
from juno.exchanges import map_exchanges
from juno.plugins import list_plugins
from juno.storages import map_storages
from juno.utils import gen_random_names

_log = logging.getLogger(__name__)


async def engine() -> None:
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

    # Create configured services.
    services = {}
    services.update(map_exchanges(config, list_required_names(config, 'exchange')))
    services.update(map_storages(config, list_required_names(config, 'storage')))
    _log.info(f'services created: {", ".join(services.keys())}')

    # Create components used by configured agents.
    components = map_components(services, config, list_required_component_names(config))
    _log.info(f'components created: {", ".join(components.keys())}')

    # Create configured agents.
    agents = list_agents(components, config)

    # Load plugins.
    plugins = list_plugins(agents, config)

    async with AsyncExitStack() as stack:
        try:
            # Init services.
            await asyncio.gather(*(stack.enter_async_context(s) for s in services.values()))
            # Init components.
            await asyncio.gather(*(stack.enter_async_context(c) for c in components.values()))
            # Init agents.
            await asyncio.gather(*(stack.enter_async_context(a) for a in agents))
            # Init plugins.
            await asyncio.gather(*(stack.enter_async_context(p) for p in plugins))
            # Run configured agents.
            await asyncio.gather(*(run_agent(a, n) for a, n in zip(agents, gen_random_names())))
        except asyncio.CancelledError:
            _log.info('main task cancelled')
        except Exception:
            _log.exception('unhandled exception in main')
            raise


def handle_sigterm(signalnum: int, frame: FrameType) -> None:
    _log.info(f'SIGTERM terminating the process')
    sys.exit()


async def run_agent(agent: Agent, name: str) -> None:
    type_name = type(agent).__name__.lower()
    _log.info(f'running {name} ({type_name}): {agent.config}')
    result = await agent.start()
    _log.info(f'{name} ({type_name}) finished: {result}')


try:
    asyncio.run(engine())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
