import argparse
import asyncio
import logging

import juno.json as json
from juno.exchanges import Exchange
from juno.time import strfinterval
from juno.typing import type_to_raw

parser = argparse.ArgumentParser()
parser.add_argument("exchange", nargs="?", default="binance")
parser.add_argument("symbol", nargs="?", default="eth-btc")
parser.add_argument(
    "--dump",
    action="store_true",
    default=False,
)
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        exchange_info = await exchange.get_exchange_info()

        logging.info(exchange_info.fees.get(args.symbol) or exchange_info.fees["__all__"])
        logging.info(list(map(strfinterval, exchange.map_candle_intervals().keys())))
        logging.info(exchange_info.filters.get(args.symbol) or exchange_info.filters["__all__"])

        if args.dump:
            with open("exchange_info.json", "w") as file:
                json.dump(type_to_raw(exchange_info), file, indent=4)


asyncio.run(main())
