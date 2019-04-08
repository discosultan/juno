import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from typing import Any, Dict

from juno.agents import Agent, list_required_component_names, list_agents
from juno.components import map_components
from juno.config import list_required_names, load_from_env, load_from_json_file
from juno.exchanges import map_exchanges
from juno.storages import map_storages

_log = logging.getLogger(__name__)


async def engine() -> None:
    # Load config.
    config = {}
    config.update(load_from_json_file('config.json'))
    config.update(load_from_env())

    # Configure logging.
    logging.basicConfig(
        handlers=[logging.StreamHandler(stream=sys.stdout)],
        level=logging.getLevelName((config.get('log_level') or 'INFO').upper()))

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
    _log.info(f'agents created: {", ".join((f"{a} {c}" for a, c in agents))}')

    async with AsyncExitStack() as stack:
        try:
            # Init services.
            await asyncio.gather(*(stack.enter_async_context(s) for s in services.values()))
            # Init components.
            await asyncio.gather(*(stack.enter_async_context(c) for c in components.values()))
            # Init agents.
            await asyncio.gather(*(stack.enter_async_context(a) for a, _ in agents))
            # Init plugins.

            # Run configured agents.
            await asyncio.gather(*(handle_agent(a, c) for a, c in agents))
        except asyncio.CancelledError:
            _log.info('main task cancelled')
        except Exception as e:
            _log.error(f'unhandled exception: {e}')
            raise


async def handle_agent(agent: Agent, config: Dict[str, Any]) -> None:
    _log.info(f'running {config["name"]}: {config}')
    result = await agent.run(**{k: v for k, v in config.items() if k != 'name'})
    _log.info(f'{config["name"]} finished: {result}')


try:
    asyncio.run(engine())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
