import argparse
import asyncio
import logging
from decimal import Decimal

from juno import Balance, SavingsProduct
from juno.components import User
from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument("assets", type=lambda s: s.split(","))
parser.add_argument("size", nargs="?", type=Decimal, default=None)
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(Binance, from_env())
    user = User([exchange])
    async with exchange, user:
        products = await user.map_savings_products("binance")
        balances = (await user.map_balances("binance", ["spot"]))["spot"]
        await asyncio.gather(*(redeem_asset(user, products, balances, a) for a in args.assets))


async def redeem_asset(
    user: User,
    products: dict[str, SavingsProduct],
    balances: dict[str, Balance],
    asset: str,
) -> None:
    size = args.size
    if size is None:
        size = balances[f"ld{asset}"].available

    if size == Decimal("0.0"):
        logging.info(f"nothing to redeem for {asset}")
    else:
        product_id = products[asset].product_id
        await user.redeem_savings_product("binance", product_id, size)
        logging.info(f"redeemed {size} {asset}")


asyncio.run(main())