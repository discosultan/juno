import argparse
import asyncio
import logging

from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-s", "--symbol", default="eth-btc")
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        async with exchange.connect_stream_depth(args.symbol) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
