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
    exchange = init_instance(Binance, from_env())
    user = User([exchange])
    async with exchange, user:
        size = args.size
        if size is None:
            balance = await user.get_balance("binance", "spot", args.asset)
            size = balance.available

        products = await user.map_savings_products("binance")
        product = products[args.asset]
        product_id = product.product_id

        if size < product.min_purchase_amount:
            logging.info(
                f"not enough funds to purchase {args.asset}; min required "
                f"{product.min_purchase_amount}"
            )
        else:
            await user.purchase_savings_product("binance", product_id, size)
            logging.info(f"purchased {size} worth of {args.asset}")


asyncio.run(main())
