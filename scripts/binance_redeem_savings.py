import argparse
import asyncio
from decimal import Decimal

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument("asset")
parser.add_argument("size", type=Decimal)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        products = await exchange.map_flexible_products()
        product_id = products[args.asset].product_id
        await exchange.redeem_flexible_product(product_id, args.size)


asyncio.run(main())
