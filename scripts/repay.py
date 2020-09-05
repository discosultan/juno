import argparse
import asyncio
import logging
from decimal import Decimal

from juno import exchanges
from juno.config import from_env, init_instance
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('asset', nargs='?', default='eth')
parser.add_argument('size', nargs='?', type=Decimal, default=None)
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('-a', '--account', default='margin')
args = parser.parse_args()


async def main() -> None:
    async with init_instance(get_module_type(exchanges, args.exchange), from_env()) as client:
        size = args.size
        if size is None:
            balance = (await client.map_balances(account=args.account))[args.asset]
            size = balance.borrowed + balance.interest
        await client.repay(args.asset, size, args.account)
        logging.info(
            f'repaid {balance.borrowed} borrowed + {balance.interest} interest {args.asset} '
            f'({size} total) from {args.account} account'
        )

asyncio.run(main())
