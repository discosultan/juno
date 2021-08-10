import argparse
import asyncio
import logging
from decimal import Decimal

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument("product_id")
parser.add_argument("size", type=Decimal)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        await exchange.purchase_flexible_product(args.product_id, args.size)


asyncio.run(main())
