import argparse
import asyncio
import logging
from decimal import Decimal

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('assets', nargs='?', type=lambda s: s.split(','), default='btc')
parser.add_argument('from_account', nargs='?', default='margin')
parser.add_argument('to_account', nargs='?', default='spot')
parser.add_argument('-s', '--size', nargs='?', type=Decimal, default=None)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        await asyncio.gather(*(transfer_asset(client, a) for a in args.assets))


async def transfer_asset(client: Binance, asset: str) -> None:
    size = args.size
    if not size:
        balances = await client.map_balances(account=args.from_account)
        size = balances[asset].available
    await client.transfer(
        asset=asset, size=size, from_account=args.from_account, to_account=args.to_account
    )
    logging.info(
        f'transferred {size} {asset} from {args.from_account} to {args.to_account} account'
    )


asyncio.run(main())
