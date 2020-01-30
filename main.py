import asyncio
import inspect
import logging
import signal
import sys
from contextlib import AsyncExitStack
from types import FrameType
from typing import Any, Dict, List

import pkg_resources

import juno
from juno import agents, components, config
from juno.agents import Agent
from juno.asyncio import cancelable
from juno.brokers import Broker
from juno.di import Container
from juno.exchanges import Exchange
from juno.logging import create_handlers
from juno.optimization import Solver
from juno.plugins import list_plugins
from juno.storages import Storage
from juno.utils import exc_traceback, full_path, map_module_types

_log = logging.getLogger(__name__)


async def main() -> None:
    # Load config.
    # NB: Careful with logging config. It contains sensitive data. Use
    # `juno.utils.replace_secrets` to erase secrets from the output.
    config_path = (
        sys.argv[1] if len(sys.argv) >= 2 else full_path(__file__, 'config/default.json')
    )
    cfg = {}
    cfg.update(config.from_json_file(config_path))
    cfg.update(config.from_env())

    # Configure logging.
    log_level = cfg.get('log_level', 'info')
    log_format = cfg.get('log_format', 'default')
    log_outputs = cfg.get('log_outputs', ['stdout'])
    logging.basicConfig(
        handlers=create_handlers(log_format, log_outputs),
        level=logging.getLevelName(log_level.upper())
    )

    try:
        _log.info(f'version: {pkg_resources.get_distribution(juno.__name__)}')
    except pkg_resources.DistributionNotFound:
        pass

    _log.info(f'log level: {log_level}; format: {log_format}; outputs: {log_outputs}')

    # Configure signals.
    def handle_sigterm(signalnum: int, frame: FrameType) -> None:
        _log.info(f'SIGTERM terminating the process')
        sys.exit()

    signal.signal(signal.SIGTERM, handle_sigterm)

    # Configure loop exception handling.
    def custom_exception_handler(loop, context):
        # TODO: walrus
        exc = context.get('exception')
        if exc:
            _log.error(exc_traceback(exc))
        _log.info('custom loop exception handler; cancelling all tasks')
        loop.default_exception_handler(context)
        for task in (task for task in asyncio.all_tasks() if not task.done()):
            task.cancel()

    asyncio.get_running_loop().set_exception_handler(custom_exception_handler)

    # Configure deps.
    container = Container()
    container.add_singleton_instance(Dict[str, Any], lambda: cfg)
    container.add_singleton_instance(Storage, lambda: config.init_instance(Storage, cfg))
    # container.add_singleton_instance(
    #     List[Exchange], lambda: config.init_instances_mentioned_in_config(Exchange, cfg)
    # )
    container.add_singleton_instance(
        List[Exchange], lambda: config.try_init_all_instances(Exchange, cfg)
    )
    container.add_singleton_type(Broker, lambda: config.resolve_concrete(Broker, cfg))
    container.add_singleton_type(Solver, lambda: config.resolve_concrete(Solver, cfg))
    for _name, type_ in inspect.getmembers(components, inspect.isclass):
        container.add_singleton_type(type_)

    # Load agents.
    agent_types = map_module_types(agents)
    agent_config_map: Dict[Agent, Dict[str, Any]] = {
        container.resolve(agent_types[c['type']]): c for c in cfg['agents']
    }

    # Load plugins.
    plugins = list_plugins(agent_config_map, cfg)

    async with AsyncExitStack() as stack:

        # Init all deps and plugins.
        await asyncio.gather(
            stack.enter_async_context(container), *(stack.enter_async_context(p) for p in plugins)
        )

        # Run agents.
        await asyncio.gather(
            *(a.start(**config.kwargs_for(a.run, c)) for a, c in agent_config_map.items())
        )

    _log.info('main finished')


try:
    asyncio.run(cancelable(main()))
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')
except BaseException:
    _log.exception('unhandled error in program')
    sys.exit(1)
finally:
    _log.info('program exiting')
