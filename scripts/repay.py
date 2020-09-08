import argparse
import asyncio
import logging
from decimal import Decimal

from juno import exchanges
from juno.components import Wallet
from juno.config import from_env, init_instance
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('asset', nargs='?', default='eth')
parser.add_argument('size', nargs='?', type=Decimal, default=None)
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('-a', '--account', default='margin')
args = parser.parse_args()


async def main() -> None:
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    wallet = Wallet(exchanges=[client])
    async with client, wallet:
        size = args.size
        if size is None:
            balance = await wallet.get_balance(
                exchange=args.exchange, account=args.account, asset=args.asset
            )
            size = balance.borrowed + balance.interest
        await client.repay(args.asset, size, args.account)
        logging.info(
            f'repaid {balance.borrowed} borrowed + {balance.interest} interest {args.asset} '
            f'({size} total) from {args.account} account'
        )

asyncio.run(main())
