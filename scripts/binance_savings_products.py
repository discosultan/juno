import argparse
import asyncio
import logging

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
            logging.info(products[args.asset])
        else:
            logging.info(products)

        if args.asset:
            logging.info("your subscription")
            logging.info(await exchange.get_savings_product_position(args.asset))


asyncio.run(main())
