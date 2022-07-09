import argparse
import asyncio
import logging

from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-a", "--account", default="spot")
parser.add_argument("-s", "--symbol", default=None)
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        orders = await exchange.list_orders(account=args.account, symbol=args.symbol)
        logging.info(orders)


asyncio.run(main())
