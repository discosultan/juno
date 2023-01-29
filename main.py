import asyncio
import logging
import signal
import sys
from asyncio import tasks
from typing import Any

import pkg_resources
from mergedeep import merge

import juno
from juno import agents, components, config, custodians, serialization, traders
from juno.agents import Agent
from juno.brokers import Broker
from juno.custodians import Custodian
from juno.di import Container
from juno.exchanges import Exchange
from juno.inspect import map_concrete_module_types
from juno.logging import create_handlers
from juno.path import full_path
from juno.plugins import Plugin, map_plugin_types
from juno.statistics import Statistician
from juno.storages import Storage
from juno.traders import Trader

_log = logging.getLogger(__name__)


async def main() -> None:
    # When the program is cancelled with a keyboard interrupt, SIGINT or SIGTERM, cancel only the
    # main task. The main task takes care of cancelling all of its' child tasks.
    # https://stackoverflow.com/q/66640329/1466456
    main_task: asyncio.Task = tasks.current_task()  # type: ignore
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: main_task.cancel())
    loop.add_signal_handler(signal.SIGTERM, lambda: main_task.cancel())

    # Load config.
    # NB: Careful with logging config. It contains sensitive data.
    config_path = sys.argv[1] if len(sys.argv) >= 2 else full_path(__file__, "config/default.json")
    cfg = merge(
        {},
        config.from_file(config_path),
        config.from_env(),
    )

    # Configure logging.
    log_level = cfg.get("log_level", "info")
    log_format = cfg.get("log_format", "default")
    log_outputs = cfg.get("log_outputs", ["stdout"])
    log_directory = cfg.get("log_directory", "logs")
    log_backup_count = cfg.get("log_backup_count", 0)
    logging.basicConfig(
        handlers=create_handlers(log_format, log_outputs, log_directory, log_backup_count),
        level=logging.getLevelName(log_level.upper()),
    )

    try:
        _log.info(f"version: {pkg_resources.get_distribution(juno.__name__)}")
    except pkg_resources.DistributionNotFound:
        pass

    _log.info(f"log level: {log_level}; format: {log_format}; outputs: {log_outputs}")

    # Configure deps.
    container = Container()
    container.add_singleton_instance(dict[str, Any], lambda: cfg)
    container.add_singleton_instance(Storage, lambda: config.init_instance(Storage, cfg))
    container.add_singleton_instance(
        list[Exchange], lambda: config.init_instances_mentioned_in_config(Exchange, cfg)
    )
    # container.add_singleton_instance(
    #     list[Exchange], lambda: config.try_init_all_instances(Exchange, cfg)
    # )
    container.add_singleton_type(Broker, lambda: config.resolve_concrete(Broker, cfg))
    trader_types = map_concrete_module_types(traders, Trader).values()
    container.add_singleton_types(trader_types)
    container.add_singleton_instance(
        list[Trader], lambda: list(map(container.resolve, trader_types))
    )
    custodian_types = map_concrete_module_types(custodians, Custodian).values()
    container.add_singleton_types(custodian_types)
    container.add_singleton_instance(
        list[Custodian], lambda: list(map(container.resolve, custodian_types))
    )
    container.add_singleton_types(map_concrete_module_types(components).values())
    container.add_singleton_type(Statistician)

    # Load agents and plugins.
    agent_types: dict[str, type[Agent]] = map_concrete_module_types(agents)
    plugin_types = map_plugin_types(config.list_names(cfg, "plugin"))
    agent_ctxs: list[tuple[Agent, Any, list[Plugin]]] = [
        (
            container.resolve(agent_types[c["type"]]),
            serialization.config.deserialize(c, agent_types[c["type"]].Config),
            [container.resolve(plugin_types[p]) for p in c.get("plugins", [])],
        )
        for c in cfg["agents"]
    ]

    # Enter deps.
    async with container:
        # Run agents.
        await asyncio.gather(*(a.run(c, p) for a, c, p in agent_ctxs))

    _log.info("main finished")


try:
    asyncio.run(main())
except asyncio.CancelledError:
    _log.info("program cancelled")
except KeyboardInterrupt:
    _log.info("program interrupted by keyboard")
except BaseException:
    _log.exception("unhandled error in program")
    sys.exit(1)
finally:
    _log.info("program exiting")
