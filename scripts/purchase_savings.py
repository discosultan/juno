import argparse
import asyncio
import logging
from decimal import Decimal

from juno import Asset, Balance, SavingsProduct
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
        await asyncio.gather(*(purchase_asset(user, products, balances, a) for a in args.assets))


async def purchase_asset(
    user: User,
    products: dict[Asset, SavingsProduct],
    balances: dict[Asset, Balance],
    asset: Asset,
) -> None:
    size = args.size
    if size is None:
        size = balances[asset].available

    product = products[asset]
    product_id = product.product_id

    size = min(size, product.max_purchase_amount_for_user)

    if size < product.min_purchase_amount:
        logging.info(
            f"not enough funds to purchase {asset}; min required " f"{product.min_purchase_amount}"
        )
    else:
        await user.purchase_savings_product("binance", product_id, size)
        logging.info(f"purchased {size} worth of {asset}")


asyncio.run(main())
