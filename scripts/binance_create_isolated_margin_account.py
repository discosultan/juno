import argparse
import asyncio

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?', default='eth-btc')
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        await client.create_isolated_margin_account(args.symbol)

asyncio.run(main())
