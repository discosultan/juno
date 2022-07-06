import asyncio
import logging
from dataclasses import asdict

from juno.components import Informant
from juno.exchanges import Exchange
from juno.path import save_json_file
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
        save_json_file(
            (asdict(fees), asdict(filters)), f"{EXCHANGE}_{SYMBOL}_fees_filters.json", indent=4
        )


asyncio.run(main())
