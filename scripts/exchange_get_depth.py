import argparse
import asyncio
import logging

from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-s", "--symbol", default="btc-usdt")
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        val = await exchange.get_depth(args.symbol)
    logging.info(val)


asyncio.run(main())
