import asyncio
from contextlib import AsyncExitStack
import inspect
import logging
import os
import sys

from juno.agents import new_agent
import juno.components
import juno.exchanges
import juno.storages


_log = logging.getLogger(__name__)


async def engine():
    logging.basicConfig(
        handlers=[logging.StreamHandler(stream=sys.stdout)],
        level=logging.getLevelName(os.getenv('JUNO_LOGGING_LEVEL', default='DEBUG')))

    config = {
        'exchanges': ['binance'],
        'storage': 'sqlite',
        'symbols': ['eth-btc']
    }

    services = {}

    for name, exchange_type in inspect.getmembers(juno.exchanges, inspect.isclass):
        keys = exchange_type.__init__.__annotations__.keys()  # type: ignore
        kwargs = {key: os.getenv(f'JUNO_{name.upper()}_{key.upper()}') for key in keys}
        if all(kwargs.values()):
            services[name.lower()] = exchange_type(**kwargs)  # type: ignore

    for name, storage_type in inspect.getmembers(juno.storages, inspect.isclass):
        services[name.lower()] = storage_type()

    components = {}

    for name, component_type in inspect.getmembers(juno.components, inspect.isclass):
        components[name.lower()] = component_type(services=services, config=config)

    async with AsyncExitStack() as stack:
        try:
            # Init services.
            await asyncio.gather(
                *(stack.enter_async_context(s) for s in services.values()))
            # Init components.
            await asyncio.gather(
                *(stack.enter_async_context(c) for c in components.values()))
            # Run agents.
            await asyncio.gather(
                *(new_agent(components, settings) for settings in config['agents']))
        except asyncio.CancelledError:
            _log.info('main task cancelled')
        except Exception as e:
            _log.error(f'unhandled exception: {e}')
            raise


try:
    asyncio.run(engine())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
