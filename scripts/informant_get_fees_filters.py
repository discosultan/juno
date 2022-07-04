import asyncio
import logging
from dataclasses import asdict

from juno import json
from juno.components import Informant
from juno.exchanges import Exchange
from juno.storages import SQLite

EXCHANGE = "binance"
SYMBOL = "eth-btc"

DUMP_AS_JSON = False


async def main() -> None:
    storage = SQLite()
    exchange = Exchange.from_env(EXCHANGE)
    informant = Informant(storage, [exchange])
    async with exchange, informant:
        fees, filters = informant.get_fees_filters(EXCHANGE, SYMBOL)
        logging.info(fees)
        logging.info(filters)

    if DUMP_AS_JSON:
        with open(f"{EXCHANGE}_{SYMBOL}_fees_filters.json", "w") as f:
            json.dump((asdict(fees), asdict(filters)), f, indent=4)


asyncio.run(main())
