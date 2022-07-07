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
        async with exchange.connect_stream_trades(symbol=args.symbol) as stream:
            i = 0
            async for val in stream:
                logging.info(val)
                i += 1
                if i == 2:
                    break


asyncio.run(main())
