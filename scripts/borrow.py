import argparse
import asyncio
import logging
from decimal import Decimal

from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("asset", nargs="?", default="eth")
parser.add_argument("size", nargs="?", type=Decimal, default=None)
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-a", "--account", default="margin")
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        size = args.size
        if size is None:
            size = Decimal("0.0000_0001")
        await exchange.borrow(args.asset, size, args.account)
        logging.info(f"borrowed {size} {args.asset} to {args.account} account")


asyncio.run(main())
