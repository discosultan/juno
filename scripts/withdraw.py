import argparse
import asyncio
from decimal import Decimal

from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("asset", nargs="?")
parser.add_argument("address", nargs="?")
parser.add_argument("amount", nargs="?", type=Decimal)
parser.add_argument("-e", "--exchange", default="binance")
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        await exchange.withdraw(args.asset, args.address, args.amount)


asyncio.run(main())
