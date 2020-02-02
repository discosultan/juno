import asyncio
import logging

import juno.json as json
from juno import exchanges
from juno.components import Informant
from juno.config import from_env, init_instance
from juno.storages import SQLite

EXCHANGE_TYPE = exchanges.Binance
SYMBOL = 'eth-btc'

DUMP_AS_JSON = False


async def main() -> None:
    storage = SQLite()
    config = from_env()
    exchange = init_instance(EXCHANGE_TYPE, config)
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    informant = Informant(storage, [exchange])
    async with exchange, informant:
        fees, filters = informant.get_fees_filters(exchange_name, SYMBOL)
        logging.info(fees)
        logging.info(filters)

    if DUMP_AS_JSON:
        with open(f'{exchange_name}_{SYMBOL}_fees_filters.json', 'w') as f:
            json.dump((fees, filters), f, indent=4)

    logging.info('done')


asyncio.run(main())
