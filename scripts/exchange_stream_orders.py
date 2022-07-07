import argparse
import asyncio
import logging

from juno.exchanges import Exchange

SYMBOL = "eth-btc"

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("account", nargs="?", default="spot")
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as client:
        async with client.connect_stream_orders(account=args.account, symbol=SYMBOL) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
