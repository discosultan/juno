import argparse
import asyncio
import logging
from decimal import Decimal

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('asset', nargs='?', default='eth')
parser.add_argument('size', nargs='?', type=Decimal, default=None)
parser.add_argument(
    '-b', '--borrow',
    action='store_true',
    default=False,
    help='if set, borrow; otherwise repay',
)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        size = args.size
        if args.borrow:
            if size is None:
                size = Decimal('0.0000_0001')
            await client.borrow(args.asset, size)
        else:
            if size is None:
                balance = (await client.map_balances(margin=True))[args.asset]
                size = balance.borrowed + balance.interest
            await client.repay(args.asset, size)
        logging.info(f'{"borrowed" if args.borrow else "repaid"} {size} {args.asset}')

asyncio.run(main())
