import asyncio
from contextlib import AsyncExitStack
import logging
import os
import sys
from typing import Any, Dict

from juno.agents import map_required_component_names, run_agent
from juno.components import map_components
from juno.exchanges import map_exchanges
from juno.storages import map_storages


_log = logging.getLogger(__name__)


async def engine() -> None:
    logging.basicConfig(
        handlers=[logging.StreamHandler(stream=sys.stdout)],
        level=logging.getLevelName(os.getenv('JUNO_LOGGING_LEVEL', default='DEBUG')))

    config: Dict[str, Any] = {
        'exchanges': ['binance'],
        'storage': 'sqlite',
        'symbols': ['eth-btc']
    }

    # Create all services.
    services = {}
    services.update(map_exchanges())
    services.update(map_storages())

    # Create components used by configured agents.
    required_component_names = map_required_component_names((a['name'] for a in config['agents']))
    components = map_components(required_component_names, services, config)

    async with AsyncExitStack() as stack:
        try:
            # Init services.
            await asyncio.gather(
                *(stack.enter_async_context(s) for s in services.values()))
            # Init components.
            await asyncio.gather(
                *(stack.enter_async_context(c) for c in components.values()))
            # Run configured agents.
            await asyncio.gather(*(run_agent(components, c) for c in config['agents']))
        except asyncio.CancelledError:
            _log.info('main task cancelled')
        except Exception as e:
            _log.error(f'unhandled exception: {e}')
            raise


try:
    asyncio.run(engine())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
