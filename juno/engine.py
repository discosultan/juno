import asyncio
from contextlib import AsyncExitStack
import inspect
import logging
import os
import sys

import juno.components
import juno.exchanges
import juno.storages


_log = logging.getLogger(__name__)


class Engine:

    def __init__(self):
        logging.basicConfig(
            handlers=[logging.StreamHandler(stream=sys.stdout)],
            level=logging.getLevelName(os.getenv('JUNO_LOGGING_LEVEL', default='DEBUG')))

        self.config = {
            'exchanges': ['binance'],
            'storage': 'sqlite',
            'symbols': ['eth-btc']
        }

        self.services = {}

        print(inspect.getmembers(juno.exchanges, inspect.isclass))

        for name, exchange_type in inspect.getmembers(juno.exchanges, inspect.isclass):
            keys = exchange_type.__init__.__annotations__.keys()  # type: ignore
            kwargs = {key: os.getenv(f'JUNO_{name.upper()}_{key.upper()}') for key in keys}
            if all(kwargs.values()):
                self.services[name.lower()] = exchange_type(**kwargs)  # type: ignore

        for name, storage_type in inspect.getmembers(juno.storages, inspect.isclass):
            self.services[name.lower()] = storage_type()

        self.components = {}

        for name, component_type in inspect.getmembers(juno.components, inspect.isclass):
            self.components[name.lower()] = component_type(services=self.services,
                                                           config=self.config)

    async def main(self):
        async with AsyncExitStack() as stack:
            try:
                # Init services.
                await asyncio.gather(
                    *(stack.enter_async_context(s) for s in self.services.values()))
                # Init components.
                await asyncio.gather(
                    *(stack.enter_async_context(c) for c in self.components.values()))
                # Run engine.
                await self.run()
            except asyncio.CancelledError:
                _log.info('main task cancelled')
            except Exception as e:
                _log.error(f'unhandled exception: {e}')
                raise

    async def run(self):
        pass
