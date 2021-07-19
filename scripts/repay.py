import argparse
import asyncio
import logging
from decimal import Decimal

from juno.components import User
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("account", nargs="?", default="margin")
parser.add_argument("asset", nargs="?", default="eth")
parser.add_argument("size", nargs="?", type=Decimal, default=None)
parser.add_argument("-e", "--exchange", default="binance")
args = parser.parse_args()


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    user = User(exchanges=[exchange])
    async with exchange, user:
        size = args.size
        if size is None:
            balance = await user.get_balance(
                exchange=args.exchange, account=args.account, asset=args.asset
            )
            size = balance.borrowed + balance.interest
        await exchange.repay(args.asset, size, args.account)
        logging.info(
            f"repaid {balance.borrowed} borrowed + {balance.interest} interest {args.asset} "
            f"({size} total) from {args.account} account"
        )


asyncio.run(main())
