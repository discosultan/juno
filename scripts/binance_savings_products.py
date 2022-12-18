import argparse
import asyncio
import logging
from typing import Any

import juno.json as json
from juno import serialization
from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument("asset", nargs="?")
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        products = await exchange.map_savings_products()
        logging.info("savings products")
        if args.asset:
            log_info_pretty(products[args.asset])
        else:
            log_info_pretty(products)

        position = await exchange.get_savings_product_position(args.asset)
        logging.info("your subscription")
        log_info_pretty(position)


def log_info_pretty(value: Any) -> None:
    logging.info(json.dumps(serialization.raw.serialize(value), indent=4))


asyncio.run(main())
