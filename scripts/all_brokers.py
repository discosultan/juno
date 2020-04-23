import asyncio
import itertools
import logging

from juno import config
from juno.brokers import Broker, Limit, Market
from juno.components import Informant, Orderbook
from juno.exchanges import Binance, Coinbase, Exchange
from juno.storages import SQLite


async def main() -> None:
    cfg = config.from_env()
    exchanges = [
        config.init_instance(Binance, cfg),
        config.init_instance(Coinbase, cfg),
    ]
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config=cfg)
    brokers = [
        Market(informant=informant, orderbook=orderbook, exchanges=exchanges),
        Limit(informant=informant, orderbook=orderbook, exchanges=exchanges),
    ]
    async with exchanges[0], exchanges[1], informant, orderbook:
        for (exchange, broker) in itertools.product(exchanges, brokers):
            await buy_sell(exchange, broker)


async def buy_sell(exchange: Exchange, broker: Broker) -> None:
    logging.info('TODO')
    pass


asyncio.run(main())
