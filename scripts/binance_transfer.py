import argparse
import asyncio
import logging
from decimal import Decimal

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('asset', nargs='?', default='btc')
parser.add_argument('size', nargs='?', type=Decimal, default=None)
parser.add_argument(
    '-m', '--margin',
    action='store_true',
    default=False,
    help='if set, transfer from spot to margin; otherwise from margin to spot account',
)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        size = args.size
        if not size:
            balances = await client.map_balances(margin=not args.margin)
            size = balances[args.asset].available
        await client.transfer(asset=args.asset, size=size, margin=args.margin)
        logging.info(
            f'transferred {size} {args.asset} to {"margin" if args.margin else "spot"} account'
        )

asyncio.run(main())
