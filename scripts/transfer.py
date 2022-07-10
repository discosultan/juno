import argparse
import asyncio
import logging
from decimal import Decimal

from juno import Asset
from juno.components import User
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("from_account", nargs="?", default="margin")
parser.add_argument("to_account", nargs="?", default="spot")
parser.add_argument("assets", nargs="?", type=lambda s: s.split(","), default="btc")
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-s", "--size", nargs="?", type=Decimal, default=None)
args = parser.parse_args()


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    user = User([exchange])
    async with exchange, user:
        await asyncio.gather(*(transfer_asset(user, exchange, a) for a in args.assets))


async def transfer_asset(user: User, exchange: Exchange, asset: Asset) -> None:
    size = args.size
    if not size:
        balance = await user.get_balance(
            exchange=args.exchange, account=args.from_account, asset=asset
        )
        size = balance.available
    await exchange.transfer(
        asset=asset, size=size, from_account=args.from_account, to_account=args.to_account
    )
    logging.info(
        f"transferred {size} {asset} from {args.from_account} to {args.to_account} account"
    )


asyncio.run(main())
