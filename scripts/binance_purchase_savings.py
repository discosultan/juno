import argparse
import asyncio
import logging
from decimal import Decimal

from juno.components import User
from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument("asset")
parser.add_argument("size", nargs="?", type=Decimal, default=None)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        size = args.size
        if size is None:
            async with User([exchange]) as user:
                balance = await user.get_balance("binance", "spot", args.asset)
                size = balance.available

        products = await exchange.map_flexible_products()
        product = products[args.asset]
        product_id = product.product_id

        if size < product.min_purchase_amount:
            logging.info(
                f"not enough funds to purchase {args.asset}; min required "
                f"{product.min_purchase_amount}"
            )
        else:
            await exchange.purchase_flexible_product(product_id, size)
            logging.info(f"purchased {size} worth of {args.asset}")


asyncio.run(main())
