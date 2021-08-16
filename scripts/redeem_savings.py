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
            savings_balance = await user.get_balance("binance", "spot", f"ld{args.asset}")
            size = savings_balance.available

        if size == Decimal("0.0"):
            logging.info("nothing to redeem")
        else:
            products = await user.map_savings_products("binance")
            product_id = products[args.asset].product_id
            await user.redeem_savings_product("binance", product_id, size)
            logging.info(f"redeemed {size} {args.asset}")


asyncio.run(main())
