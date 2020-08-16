import argparse
import asyncio

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('assets', type=lambda s: s.split(','))
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        await client.convert_dust(args.assets)

asyncio.run(main())
